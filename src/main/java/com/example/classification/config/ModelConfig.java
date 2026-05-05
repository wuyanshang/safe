package com.example.classification.config;

import lombok.Data;

@Data
public class ModelConfig {

    private String name;
    private String apiKey;
    private String baseUrl;
    private String model;
}
