package com.tactivision.backend.controller;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins = {
    "http://localhost:5173",
    "https://tactivision-frontend.onrender.com"
})

public class HelloController {

    private final JdbcTemplate jdbcTemplate;

    public HelloController(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello from TactiVision IA Backend";
    }

    @GetMapping("/status")
    public Map<String, String> status() {

        String databaseStatus = jdbcTemplate.queryForObject(
                "SELECT status FROM system_status WHERE name = 'TactiVision'",
                String.class
        );

        return Map.of(
                "backend", "OK",
                "database", databaseStatus != null ? "CONNECTED" : "ERROR"
        );
    }
}