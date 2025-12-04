**使用概览**
- 通过 `dataloader.load()` 读取数据，返回字典 `info`，包含四个主键：
  - `"车次信息"`: `dict[int, TrainService]`
  - `"列车停站股道"`: `dict[int, list[str]]`
  - `"列车通过股道"`: `dict[tuple[int, int], str]`
  - `"运行标尺"`: `dict[tuple[int, int, int], RunRuler]`
 - 代码位置：`dataloader.py:56` 定义 `load()`；字典的构造与返回在 `dataloader.py:157-162`。

**数据结构**
 - `TrainService`（`dataloader.py:44-53`）
    - `id`: 车次 ID（`int`）
    - `ideally_time_setoff`: 理想出发时间（`int` 秒）
    - `ideally_time_achieve`: 理想到达时间（`int` 秒）
    - `path`: 该车次途径的站点列表（`list[TrainStation]`）
 - `TrainStation`（`dataloader.py:31-42`）
    - `id`: 车站 ID（如 CSV 的 `车站名称`/`车站` 中的编号，已去掉“站”前缀）（`int`）
    - `ruler_info`: 该站关联的运行标尺（`RunRuler` 或 `None`，见下）
    - `stop_time_range`: 停站时间范围（`tuple[int, int]`）
    - `stop_strategy`: 停站策略（`str`，如“必停/选停/禁停”等）
 - `RunRuler`（`dataloader.py:17-28`）
    - `type`: 区间行别（`"上行"` 或 `"下行"`）
    - `runtime`: 运行时间
    - `start`: 起车附加
    - `stop`: 停车附加
    - `property`: 区间性质（`"单线"`、`"双线"`）

**快速上手**
```python
from dataloader import load

info = load()

# 车次信息字典：tid -> TrainService
checi = info['车次信息']
for tid, ts in checi.items():
    print('车次ID', tid,
          '理想发车', ts.ideally_time_setoff,
          '理想到达', ts.ideally_time_achieve)

    # 遍历途径站点
    for st in ts.path:
        print('站点ID', st.id,
              '停站策略', st.stop_strategy,
              '停站范围', st.stop_time_range,
              '理想停站', st.is_ideal_stop)

        # 如有运行标尺，读取行别、性质与参数
        if st.ruler_info is not None:
            r = st.ruler_info
            print('行别:', r.type, '性质:', r.property,
                  '参数(运行/起车附加/停车附加):', r.runtime, r.start, r.stop)
```

**查询股道数据**
- 停站股道（某站的可停站股道集合）：
```python
stop_tracks = info['列车停站股道']  # dict[int, list[str]]
station_id = 738
tracks = stop_tracks.get(station_id, [])
print('站', station_id, '可停站股道:', tracks)
```
- 通过股道（某车次在某站的通过股道）：
```python
pass_tracks = info['列车通过股道']  # dict[tuple[int, int], str]
tid, station_id = 1, 738
track = pass_tracks.get((tid, station_id))
print('车次', tid, '站', station_id, '通过股道:', track)
```

**查询运行标尺**
- 直接通过 `TrainStation.ruler_info` 获取标尺对象（推荐）：
```python
for ts in info['车次信息'].values():
    for st in ts.path:
        if st.ruler_info:
            print('站', st.id,
                  '行别:', st.ruler_info.type,
                  '性质:', st.ruler_info.property,
                  '运行时分:', st.ruler_info.runtime)
```
- 或使用标尺索引字典：键为 `(标尺编号, 运行区间左端点, 运行区间右端点)`，如 `(360, 4950, 738)`（`dataloader.py:63-80` 构建）：
```
run_ruler = info['运行标尺']
rid, s0, s1 = 360, 4950, 738
rr = run_ruler.get((rid, s0, s1))
if rr:
    print('运行标尺', rid,
          '行别:', rr.type,
          '性质:', rr.property,
          '运行时分:', rr.runtime,
          '起车附加:', rr.start,
          '停车附加:', rr.stop)
```

