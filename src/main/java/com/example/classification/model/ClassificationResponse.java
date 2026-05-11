package com.example.classification.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

/**
 * Agent 分类响应 JSON 结构
 */
@Data
public class ClassificationResponse {

    @JsonProperty("is_suspected_sensitive")
    private boolean isSuspectedSensitive;

    private String reason;
}
