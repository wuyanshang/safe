package com.example.classification.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
public class SensitiveResponse {

    @JsonProperty("is_suspected_sensitive")
    private boolean isSuspectedSensitive;

    @JsonProperty("catalog_node")
    private String catalogNode;

    private String reason;
}
