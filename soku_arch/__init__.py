# SPDX-License-Identifier: MIT
# 本项目自有代码(用户裁定 2026-10-18) — vendor 于本项目仓库, 见 VENDORED.md
# -*- coding: utf-8 -*-
"""soku_arch —— 非想天则本地对战小模型架构（从零构建）。

模块职责：
  constants  权威领域常量（天气/角色/宏库规模/特征语义），全部注明来源
  schema     有效性、标准化、合法性掩码、已知死列
  dataset    加载/体检/切分（含防泄漏的 block 切分与泄漏量化用的 random 切分）
  model      MacroPolicyNet（可训练）+ SequoiaSeqNet（时序，待数据契约）
  losses     类平衡 CE + 标签平滑 + 多任务
  metrics    top-k / macro-F1 / 各类召回 / ECE / JS / 覆盖
  train      训练 CLI
  export_onnx / bench / runtime_numpy   部署链路
  eval_protocol / rule_ai              对战评估协议（在线部分需真机）
"""
from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
