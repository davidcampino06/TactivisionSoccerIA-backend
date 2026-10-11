"""Data structures used by the backend, each one for a concrete need.

- Array (Python list / NumPy in the AI Service): ordered, indexed collections such as
  frames, detections and indicator values.
- Stack (LIFO):  version history of a tactical play -> "undo" goes back to the previous version.
- Queue (FIFO):  pending video analyses -> processed in arrival order, one at a time.
- DoublyLinkedList: chronological match timeline -> each match knows its previous and next
  match, used for team evolution (deltas between consecutive matches) and navigation.
- HashTable (separate chaining): failed login attempts per e-mail -> O(1) average lookup to
  decide whether an account is temporarily locked.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


class EmptyStructureError(IndexError):
    """Raised when reading from an empty stack or queue."""


class Stack(Generic[T]):
    """LIFO stack backed by a dynamic array (Python list)."""

    def __init__(self, items: list[T] | None = None) -> None:
        self._items: list[T] = list(items or [])

    def push(self, item: T) -> None:
        self._items.append(item)

    def pop(self) -> T:
        if not self._items:
            raise EmptyStructureError("pop from empty stack")
        return self._items.pop()

    def peek(self) -> T:
        if not self._items:
            raise EmptyStructureError("peek from empty stack")
        return self._items[-1]

    def is_empty(self) -> bool:
        return not self._items

    def __len__(self) -> int:
        return len(self._items)


class Queue(Generic[T]):
    """Thread-safe FIFO queue. ``get`` blocks until an item is available."""

    def __init__(self) -> None:
        self._items: deque[T] = deque()
        self._condition = threading.Condition()

    def enqueue(self, item: T) -> int:
        """Add an item and return its position (1 = next to be processed)."""
        with self._condition:
            self._items.append(item)
            self._condition.notify()
            return len(self._items)

    def dequeue(self, timeout: float | None = None) -> T:
        with self._condition:
            if not self._condition.wait_for(lambda: bool(self._items), timeout=timeout):
                raise EmptyStructureError("dequeue timed out on empty queue")
            return self._items.popleft()

    def position_of(self, item: T) -> int | None:
        with self._condition:
            for index, queued in enumerate(self._items):
                if queued == item:
                    return index + 1
        return None

    def remove(self, item: T) -> bool:
        with self._condition:
            try:
                self._items.remove(item)
                return True
            except ValueError:
                return False

    def is_empty(self) -> bool:
        with self._condition:
            return not self._items

    def __len__(self) -> int:
        with self._condition:
            return len(self._items)


@dataclass
class _Node(Generic[T]):
    value: T
    previous: "_Node[T] | None" = None
    next: "_Node[T] | None" = None


class DoublyLinkedList(Generic[T]):
    """Doubly linked list with O(1) append/prepend and bidirectional traversal."""

    def __init__(self) -> None:
        self._head: _Node[T] | None = None
        self._tail: _Node[T] | None = None
        self._size = 0

    def append(self, value: T) -> _Node[T]:
        node = _Node(value, previous=self._tail)
        if self._tail:
            self._tail.next = node
        else:
            self._head = node
        self._tail = node
        self._size += 1
        return node

    def prepend(self, value: T) -> _Node[T]:
        node = _Node(value, next=self._head)
        if self._head:
            self._head.previous = node
        else:
            self._tail = node
        self._head = node
        self._size += 1
        return node

    def remove(self, node: _Node[T]) -> None:
        if node.previous:
            node.previous.next = node.next
        else:
            self._head = node.next
        if node.next:
            node.next.previous = node.previous
        else:
            self._tail = node.previous
        node.previous = node.next = None
        self._size -= 1

    def find(self, predicate) -> _Node[T] | None:
        current = self._head
        while current:
            if predicate(current.value):
                return current
            current = current.next
        return None

    @property
    def head(self) -> _Node[T] | None:
        return self._head

    @property
    def tail(self) -> _Node[T] | None:
        return self._tail

    def __iter__(self) -> Iterator[T]:
        current = self._head
        while current:
            yield current.value
            current = current.next

    def reversed(self) -> Iterator[T]:
        current = self._tail
        while current:
            yield current.value
            current = current.previous

    def __len__(self) -> int:
        return self._size


class HashTable(Generic[K, V]):
    """Hash table with separate chaining (one list of (key, value) pairs per bucket).

    Average O(1) put/get/remove. When the load factor (items / buckets) passes 0.75 the table
    doubles its buckets and re-inserts every pair (rehash), keeping chains short.
    """

    MAX_LOAD_FACTOR = 0.75

    def __init__(self, capacity: int = 16) -> None:
        self._buckets: list[list[tuple[K, V]]] = [[] for _ in range(max(1, capacity))]
        self._size = 0

    def _index(self, key: K) -> int:
        return hash(key) % len(self._buckets)

    def put(self, key: K, value: V) -> None:
        bucket = self._buckets[self._index(key)]
        for position, (existing, _) in enumerate(bucket):
            if existing == key:
                bucket[position] = (key, value)
                return
        bucket.append((key, value))
        self._size += 1
        if self.load_factor > self.MAX_LOAD_FACTOR:
            self._resize(len(self._buckets) * 2)

    def get(self, key: K, default: V | None = None) -> V | None:
        for existing, value in self._buckets[self._index(key)]:
            if existing == key:
                return value
        return default

    def remove(self, key: K) -> bool:
        bucket = self._buckets[self._index(key)]
        for position, (existing, _) in enumerate(bucket):
            if existing == key:
                del bucket[position]
                self._size -= 1
                return True
        return False

    def __contains__(self, key: object) -> bool:
        return any(existing == key for existing, _ in self._buckets[hash(key) % len(self._buckets)])

    def keys(self) -> Iterator[K]:
        for bucket in self._buckets:
            for key, _ in bucket:
                yield key

    def clear(self) -> None:
        self._buckets = [[] for _ in range(len(self._buckets))]
        self._size = 0

    @property
    def load_factor(self) -> float:
        return self._size / len(self._buckets)

    @property
    def capacity(self) -> int:
        return len(self._buckets)

    def _resize(self, new_capacity: int) -> None:
        old_pairs = [pair for bucket in self._buckets for pair in bucket]
        self._buckets = [[] for _ in range(new_capacity)]
        self._size = 0
        for key, value in old_pairs:
            self.put(key, value)

    def __len__(self) -> int:
        return self._size
