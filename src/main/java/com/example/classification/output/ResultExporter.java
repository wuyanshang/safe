package com.example.classification.output;

import com.example.classification.model.ClassificationResult;
import lombok.extern.slf4j.Slf4j;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Component;

import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Slf4j
@Component
public class ResultExporter {

    private static final String[] RESULT_HEADERS = {
            "批次号", "系统中文名", "表中文名", "表英文名",
            "字段中文名", "字段英文名", "是否疑似敏感", "目录节点", "判断理由", "状态"
    };

    public void exportToExcel(List<ClassificationResult> results,
                              String outputPath, String batchNo, String fileName) throws IOException {
        Path path = Paths.get(outputPath);
        if (path.getParent() != null) {
            Files.createDirectories(path.getParent());
        }

        try (Workbook workbook = new XSSFWorkbook()) {
            CellStyle headerStyle = createHeaderStyle(workbook);
            CellStyle sensitiveStyle = createSensitiveStyle(workbook);
            CellStyle failedStyle = createFailedStyle(workbook);

            writeOverviewSheet(workbook, results, headerStyle, batchNo, fileName);
            writeResultSheet(workbook, results, headerStyle, sensitiveStyle, failedStyle);

            try (FileOutputStream fos = new FileOutputStream(outputPath)) {
                workbook.write(fos);
            }
        }

        log.info("结果导出完成: {}, 共 {} 条", outputPath, results.size());
    }

    private void writeOverviewSheet(Workbook workbook, List<ClassificationResult> results,
                                    CellStyle headerStyle, String batchNo, String fileName) {
        Sheet sheet = workbook.createSheet("总览");
        int rowIdx = 0;

        // 基本信息
        rowIdx = writeSection(sheet, rowIdx, headerStyle, "基本信息");
        rowIdx = writeKV(sheet, rowIdx, "批次号", batchNo);
        rowIdx = writeKV(sheet, rowIdx, "检测时间",
                LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
        rowIdx = writeKV(sheet, rowIdx, "输入文件", safeStr(fileName));
        rowIdx++;

        // 统计
        long total = results.size();
        long sensitiveCount = results.stream().filter(ClassificationResult::isSuspectedSensitive).count();
        long nonSensitiveCount = results.stream()
                .filter(r -> "SUCCESS".equals(r.getStatus()) && !r.isSuspectedSensitive()).count();
        long failedCount = results.stream().filter(r -> "FAILED".equals(r.getStatus())).count();

        rowIdx = writeSection(sheet, rowIdx, headerStyle, "分类统计");
        rowIdx = writeKV(sheet, rowIdx, "字段总数", String.valueOf(total));
        rowIdx = writeKV(sheet, rowIdx, "疑似敏感", sensitiveCount + " (" + pct(sensitiveCount, total) + ")");
        rowIdx = writeKV(sheet, rowIdx, "非敏感", nonSensitiveCount + " (" + pct(nonSensitiveCount, total) + ")");
        if (failedCount > 0) {
            rowIdx = writeKV(sheet, rowIdx, "检测失败", String.valueOf(failedCount));
        }
        rowIdx++;

        // 按目录节点统计
        Map<String, Long> catalogStats = results.stream()
                .filter(r -> r.isSuspectedSensitive() && r.getCatalogNode() != null)
                .collect(Collectors.groupingBy(ClassificationResult::getCatalogNode, Collectors.counting()));

        if (!catalogStats.isEmpty()) {
            rowIdx = writeSection(sheet, rowIdx, headerStyle, "按目录节点统计");
            for (Map.Entry<String, Long> entry : catalogStats.entrySet()) {
                rowIdx = writeKV(sheet, rowIdx, entry.getKey(), entry.getValue() + " 条");
            }
        }

        sheet.setColumnWidth(0, 8000);
        sheet.setColumnWidth(1, 8000);
    }

    private void writeResultSheet(Workbook workbook, List<ClassificationResult> results,
                                  CellStyle headerStyle, CellStyle sensitiveStyle, CellStyle failedStyle) {
        Sheet sheet = workbook.createSheet("分类结果");

        Row headerRow = sheet.createRow(0);
        for (int i = 0; i < RESULT_HEADERS.length; i++) {
            Cell cell = headerRow.createCell(i);
            cell.setCellValue(RESULT_HEADERS[i]);
            cell.setCellStyle(headerStyle);
        }

        for (int i = 0; i < results.size(); i++) {
            ClassificationResult r = results.get(i);
            Row row = sheet.createRow(i + 1);

            row.createCell(0).setCellValue(safeStr(r.getBatchNo()));
            row.createCell(1).setCellValue(safeStr(r.getSystemCn()));
            row.createCell(2).setCellValue(safeStr(r.getTableCn()));
            row.createCell(3).setCellValue(safeStr(r.getTableEn()));
            row.createCell(4).setCellValue(safeStr(r.getFieldCn()));
            row.createCell(5).setCellValue(safeStr(r.getFieldEn()));
            row.createCell(6).setCellValue(r.isSuspectedSensitive() ? "是" : "否");
            row.createCell(7).setCellValue(safeStr(r.getCatalogNode()));
            row.createCell(8).setCellValue(safeStr(r.getReason()));
            row.createCell(9).setCellValue(safeStr(r.getStatus()));

            // 着色
            CellStyle rowStyle = null;
            if ("FAILED".equals(r.getStatus())) {
                rowStyle = failedStyle;
            } else if (r.isSuspectedSensitive()) {
                rowStyle = sensitiveStyle;
            }
            if (rowStyle != null) {
                for (int j = 0; j < RESULT_HEADERS.length; j++) {
                    row.getCell(j).setCellStyle(rowStyle);
                }
            }
        }

        for (int i = 0; i < RESULT_HEADERS.length; i++) {
            sheet.autoSizeColumn(i);
        }
    }

    private int writeSection(Sheet sheet, int rowIdx, CellStyle headerStyle, String title) {
        Row row = sheet.createRow(rowIdx);
        Cell cell = row.createCell(0);
        cell.setCellValue(title);
        cell.setCellStyle(headerStyle);
        return rowIdx + 1;
    }

    private int writeKV(Sheet sheet, int rowIdx, String key, String value) {
        Row row = sheet.createRow(rowIdx);
        row.createCell(0).setCellValue(key);
        row.createCell(1).setCellValue(value);
        return rowIdx + 1;
    }

    private String pct(long part, long total) {
        if (total == 0) return "0%";
        return String.format("%.1f%%", part * 100.0 / total);
    }

    private CellStyle createHeaderStyle(Workbook workbook) {
        CellStyle style = workbook.createCellStyle();
        Font font = workbook.createFont();
        font.setBold(true);
        style.setFont(font);
        style.setFillForegroundColor(IndexedColors.LIGHT_BLUE.getIndex());
        style.setFillPattern(FillPatternType.SOLID_FOREGROUND);
        return style;
    }

    private CellStyle createSensitiveStyle(Workbook workbook) {
        CellStyle style = workbook.createCellStyle();
        style.setFillForegroundColor(IndexedColors.LIGHT_YELLOW.getIndex());
        style.setFillPattern(FillPatternType.SOLID_FOREGROUND);
        return style;
    }

    private CellStyle createFailedStyle(Workbook workbook) {
        CellStyle style = workbook.createCellStyle();
        style.setFillForegroundColor(IndexedColors.ROSE.getIndex());
        style.setFillPattern(FillPatternType.SOLID_FOREGROUND);
        return style;
    }

    private String safeStr(String s) {
        return s == null ? "" : s;
    }
}
