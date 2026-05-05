# -*- coding: utf-8 -*-
"""
数据安全分类分级 - 接口调用脚本
直接在 PyCharm 中运行即可
"""

import requests
import json

# ========== 配置 ==========
API_URL = "http://localhost:8080/api/classification/run"
EXCEL_FILE = r"D:\系统文件\桌面\work\quality_check\data-security-classification\input\test_data.xlsx"
# ==========================


def main():
    print(f"上传文件: {EXCEL_FILE}")
    print(f"接口地址: {API_URL}")
    print("-" * 50)

    try:
        with open(EXCEL_FILE, "rb") as f:
            files = {"file": (EXCEL_FILE.split("\\")[-1], f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            response = requests.post(API_URL, files=files, timeout=600)

        if response.status_code == 200:
            result = response.json()
            print("分类分级完成!")
            print(f"  字段总数:   {result.get('totalFields', 0)}")
            print(f"  疑似敏感:   {result.get('sensitiveCount', 0)}")
            print(f"  非敏感:     {result.get('nonSensitiveCount', 0)}")
            print(f"  失败:       {result.get('failedCount', 0)}")
            print(f"  输出文件:   {result.get('outputFile', '')}")
        else:
            print(f"请求失败, 状态码: {response.status_code}")
            print(response.text)
    except FileNotFoundError:
        print(f"文件不存在: {EXCEL_FILE}")
        print("请修改 EXCEL_FILE 变量为实际的 Excel 文件路径")
    except requests.exceptions.ConnectionError:
        print(f"无法连接到 {API_URL}")
        print("请确认 Spring Boot 服务已启动")
    except Exception as e:
        print(f"发生错误: {e}")


if __name__ == "__main__":
    main()
