package com.example.classification.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@Component
@ConfigurationProperties(prefix = "classification")
public class ClassificationProperties {

    private int maxRetries = 3;
    private int threadCount = 6;
    private String outputFile = "output/classification_result.xlsx";
}
