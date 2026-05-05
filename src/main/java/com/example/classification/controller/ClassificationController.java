package com.example.classification.controller;

import com.example.classification.config.ClassificationProperties;
import com.example.classification.model.ClassificationResult;
import com.example.classification.model.FieldInput;
import com.example.classification.output.ResultExporter;
import com.example.classification.workflow.ClassificationWorkflow;
import lombok.extern.slf4j.Slf4j;
import org.apache.poi.ss.usermodel.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/classification")
public class ClassificationController {

    private final ClassificationWorkflow workflow;
    private final ResultExporter exporter;
    private final ClassificationProperties properties;

    public ClassificationController(ClassificationWorkflow workflow,
                                    ResultExporter exporter,
                                    ClassificationProperties properties) {
        this.workflow = workflow;
        this.exporter = exporter;
        this.properties = properties;
    }

    @PostMapping("/run")
    public ResponseEntity<Map<String, Object>> run(@RequestParam("file") MultipartFile file) {
        try {
            log.info("接收到上传文件: {}", file.getOriginalFilename());
            List<FieldInput> inputs = readExcel(file.getInputStream());
            log.info("读取到 {} 条字段记录", inputs.size());

            if (inputs.isEmpty()) {
                return ResponseEntity.badRequest().body(Map.of("message", "输入数据为空"));
            }

            List<ClassificationResult> results = workflow.execute(inputs);

            String batchNo = results.isEmpty() ? "" : results.get(0).getBatchNo();
            String outputFile = properties.getOutputFile();
            exporter.exportToExcel(results, outputFile, batchNo, file.getOriginalFilename());

            long sensitiveCount = results.stream().filter(ClassificationResult::isSuspectedSensitive).count();
            long failedCount = results.stream().filter(r -> "FAILED".equals(r.getStatus())).count();

            Map<String, Object> response = new HashMap<>();
            response.put("message", "分类分级完成");
            response.put("outputFile", outputFile);
            response.put("totalFields", results.size());
            response.put("sensitiveCount", sensitiveCount);
            response.put("nonSensitiveCount", results.size() - sensitiveCount - failedCount);
            response.put("failedCount", failedCount);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error("分类分级失败: {}", e.getMessage(), e);
            return ResponseEntity.internalServerError().body(Map.of("message", "分类分级失败: " + e.getMessage()));
        }
    }

    /**
     * 读取 Excel 文件
     * 表头行：系统中文名, 表中文名, 表英文名, 字段中文名, 字段英文名
     */
    private List<FieldInput> readExcel(InputStream inputStream) throws Exception {
        List<FieldInput> inputs = new ArrayList<>();
        try (Workbook workbook = WorkbookFactory.create(inputStream)) {
            Sheet sheet = workbook.getSheetAt(0);
            for (int i = 1; i <= sheet.getLastRowNum(); i++) {
                Row row = sheet.getRow(i);
                if (row == null) continue;

                FieldInput input = new FieldInput();
                input.setSystemCn(getCellValue(row, 0));
                input.setTableCn(getCellValue(row, 1));
                input.setTableEn(getCellValue(row, 2));
                input.setFieldCn(getCellValue(row, 3));
                input.setFieldEn(getCellValue(row, 4));
                inputs.add(input);
            }
        }
        return inputs;
    }

    private String getCellValue(Row row, int colIndex) {
        Cell cell = row.getCell(colIndex);
        if (cell == null) return "";
        cell.setCellType(CellType.STRING);
        String value = cell.getStringCellValue();
        return value == null ? "" : value.trim();
    }
}
