package com.example.classification.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.List;

@Data
@Component
@ConfigurationProperties(prefix = "models")
public class ModelsProperties {

    private List<ModelConfig> configs;
    private String active;

    /**
     * 获取当前激活的模型配置
     */
    public ModelConfig getActiveConfig() {
        if (configs == null || configs.isEmpty()) {
            return null;
        }
        return configs.stream()
                .filter(c -> c.getName().equals(active))
                .findFirst()
                .orElse(configs.get(0));
    }

    /**
     * 根据名称获取模型配置
     */
    public ModelConfig getConfigByName(String name) {
        if (configs == null) {
            return null;
        }
        return configs.stream()
                .filter(c -> c.getName().equals(name))
                .findFirst()
                .orElse(null);
    }
}
