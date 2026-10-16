# Bug: W4 价值曲线自上线即死 — 2D 张量未 reshape(未修, P1)

- **发现**: 2026-10-14 从零#4 分片C(日志实证: reimu 114 次/suika 147
  次异常, "价值曲线W局均值-(n0)"恒空)。
- **症状**: learner_hub.py:281 调 value_curve.episode_values 把 [N,14400]
  2D 数组喂 conv 网; value_curve.py:19-36 无 reshape(3,60,80) — 每批
  RuntimeError, 降级响亮但**零数据**。W4 自上线起未产出过一条真曲线。
- **根因**: 复制 series_meter.aux_predict 的调用形态时, series_meter
  内部有 reshape 而此处漏(同型: 此前备忘过的"形状硬编码耦合")。
- **修复与验证**: **已修(2026-10-14晚)**: episode_values内reshape
  (-1,3,60,80)/255(series_meter同型)。配对测试test_value_curve_p1
  (mock net断言4D输入+轨迹+三段均值)全绿入C15; 实战非空曲线随
  下一learner批自检。
- **防复发**: 仪表"上线即自检"(部署验收含数据非空断言)已登记
  待仪表批次; 配对测试为最小闸门。
- **状态**: ✅已修+验证(2026-10-14晚)。
