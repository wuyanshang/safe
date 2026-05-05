package com.example.classification.model;

import lombok.Data;

@Data
public class ClassificationResult {

    // ---- 输入字段 ----
    private String batchNo;
    private String systemCn;
    private String tableCn;
    private String tableEn;
    private String fieldCn;
    private String fieldEn;

    // ---- LLM 分类结果 ----
    private boolean suspectedSensitive;
    private String catalogNode;
    private String reason;

    // ---- 状态 ----
    private String status; // SUCCESS / FAILED

    /**
     * 从 FieldInput 构建 ClassificationResult
     */
    public static ClassificationResult from(FieldInput input, String batchNo) {
        ClassificationResult result = new ClassificationResult();
        result.setBatchNo(batchNo);
        result.setSystemCn(input.getSystemCn());
        result.setTableCn(input.getTableCn());
        result.setTableEn(input.getTableEn());
        result.setFieldCn(input.getFieldCn());
        result.setFieldEn(input.getFieldEn());
        result.setStatus("PENDING");
        return result;
    }

    /**
     * 应用 LLM 响应结果
     */
    public void applyResponse(SensitiveResponse response) {
        this.suspectedSensitive = response.isSuspectedSensitive();
        this.catalogNode = response.getCatalogNode();
        this.reason = response.getReason();
        this.status = "SUCCESS";
    }

    /**
     * 标记为失败
     */
    public void markFailed(String reason) {
        this.reason = reason;
        this.status = "FAILED";
    }
}
