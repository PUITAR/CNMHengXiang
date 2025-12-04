# from enum import Enum
import pandas as pd
from dataclasses import dataclass

# 标尺信息
# @dataclass
# class RunRuler:
#     runtime_up: int = 0
#     start_up: int = 0
#     stop_up: int = 0
#     runtime_down: int = 0
#     start_down: int = 0
#     stop_down: int = 0

# 使用标尺信息
@dataclass
class RunRuler:
    # 区间行别: 上行、下行
    type: str = None
    # 运行时间
    runtime: int = 0
    # 启动时间
    start: int = 0
    # 停站时间
    stop: int = 0
    # 区间性质：单线、双线
    property: str = None

# 车站信息
@dataclass
class TrainStation:
    # 站点ID
    id: int = -1
    # 标尺信息
    ruler_info: RunRuler = None
    # 停站时间范围
    stop_time_range: tuple[int, int] = (0, 0)
    # 停站策略：必停、选停、禁停
    stop_strategy: str = None
    # 是否是理想停站
    is_ideal_stop: bool = False

# 车次信息
class TrainService:
    def __init__(self) -> None:
        # 车次ID
        self.id: int = -1
        # 理想发车时间
        self.ideally_time_setoff: int = 0
        # 理想到达时间
        self.ideally_time_achieve: int = 0
        # 车次途径站路径
        self.path: list[TrainStation] = []


# 加载数据（返回必要数据，主要是车次信息）
def load() -> dict[str, any]:
    # 列车停站股道字典：车站ID -> 停站股道列表
    fname = "data/列车停站股道.csv"
    data = pd.read_csv(fname, header=0)
    stop_tracks: dict[int, list[str]] = {}
    for idx, row in data.iterrows():
        sid = int(row['车站'].strip('站'))
        gudao = str(row['股道集合']).strip('\"').split(',')
        if sid not in stop_tracks:
            stop_tracks[sid] = gudao

    # 列车通过股道字典：(车次ID, 车站ID) -> 股道ID
    fname = "data/列车通过股道.csv"
    data = pd.read_csv(fname, header=0)
    pass_tracks: dict[tuple[int, int], str] = {}
    for idx, row in data.iterrows():
        tid = int(row['列车序号'])
        sid = int(row['车站'].strip('站'))
        gudao = row['股道集合']
        if (tid, sid) not in pass_tracks:
            pass_tracks[(tid, sid)] = gudao

    fname = "data/区间.csv"
    data = pd.read_csv(fname, header=0)
    qujian: dict[tuple[int, int], tuple[str, str]] = {}

    for idx, row in data.iterrows():
        sr = row['区间名称'].split('-')
        sr0 = int(sr[0].strip('站'))
        sr1 = int(sr[1].strip('站'))
        qujian[(sr0, sr1)] = (row['区间行别'], row['区间性质'])

    # 运行标尺信息
    # 通过标尺ID索引：(标尺名称, 区间), e.g., 运行标尺360,站4950-站738
    #   tuple[int, int, int] = (-1, -1, -1)
    fname = "data/运行标尺.csv"
    data = pd.read_csv(fname, header=0)
    run_ruler: dict[tuple[int, int, int], RunRuler] = {}
    for idx, row in data.iterrows():
        name = row['标尺名称'].strip('运行标尺')
        sr = row['区间名称'].split('-')
        sr0 = int(sr[0].strip('站'))
        sr1 = int(sr[1].strip('站'))
        type, property = qujian[(sr0, sr1)]
        run_ruler[(int(name), sr0, sr1)] = RunRuler(
            type=type,
            property=property,
            runtime=int(row['运行时分（上行）']) if type == '上行' else int(row['运行时分（下行）']),
            start=int(row['起车附加（上行）']) if type == '上行' else int(row['起车附加（下行）']),
            stop=int(row['停车附加（上行）']) if type == '上行' else int(row['停车附加（下行）']),
        )

    # 车次信息
    fname = "data/列车.csv"
    data = pd.read_csv(fname, header=0)
    checi: dict[int, TrainService] = {}

    ts = None
    for idx, row in data.iterrows():
        # print(f"xuhao: {int(row['列车序号'])}")
        if ts is None or ts.id != int(row['列车序号']):
            # print(int(row['列车序号']), ts.id if ts else None)
            if ts is not None:
                # print(len(ts.path))
                checi[ts.id] = ts
            ts = TrainService()
            # 车次ID
            ts.id = int(row['列车序号'])

        # 车次理想发车、到车时间
        if pd.notna(row['到点']) and int(row['到点']) > 0:
            ts.ideally_time_achieve = int(row['到点'])
        if pd.notna(row['发点']) and int(row['发点']) > 0:
            ts.ideally_time_setoff = int(row['发点'])

        # 车次途径站点信息
        sr = row['停站时间范围'].split(',')
        try:
            rid = int(row['运行标尺'].strip('运行标尺'))
            tmp = row['区间名称'].split('-')
            ruler_info_in_use = run_ruler[(
                rid,
                int(tmp[0].strip('站')),
                int(tmp[1].strip('站'))
            )]

        except:
            ruler_info_in_use = None
        ts.path.append(
            TrainStation(
                id=int(row['车站名称'].strip('站')),
                ruler_info=ruler_info_in_use,
                stop_time_range=(int(sr[0]), int(sr[1])),
                stop_strategy=row['停站要求'],
                is_ideal_stop=(row['理想停站'] == "是")
            )
        )

    if ts is not None:
        checi[ts.id] = ts

    return {
        '列车停站股道': stop_tracks,
        '列车通过股道': pass_tracks,
        '运行标尺': run_ruler,
        '车次信息': checi,
    }


if __name__ == '__main__':
    import pdb; 
    info = load()
    pdb.set_trace()
