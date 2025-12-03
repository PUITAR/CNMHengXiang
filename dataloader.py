# from enum import Enum
import pandas as pd
from dataclasses import dataclass

# 标尺信息
@dataclass
class RunRuler:
    runtime_up: int = 0
    start_up: int = 0
    stop_up: int = 0
    runtime_down: int = 0
    start_down: int = 0
    stop_down: int = 0

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

# 车次信息
# @dataclass
class TrainService: 
    # 车次ID
    id: int = -1
    # 理想发车时间
    ideally_time_setoff: int = 0
    # 理想到达时间
    ideally_time_achieve: int = 0
    # 车次途径站点路径
    path: list[TrainStation] = []


def load() -> list[TrainService]:
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
        run_ruler[(int(name), sr0, sr1)] = RunRuler(
            runtime_up=int(row['运行时分（上行）']),
            start_up=int(row['起车附加（上行）']),
            stop_up=int(row['停车附加（上行）']),
            runtime_down=int(row['运行时分（下行）']),
            start_down=int(row['起车附加（下行）']),
            stop_down=int(row['停车附加（下行）']),
        )

    # 车次信息
    fname = "data/列车.csv"
    data = pd.read_csv(fname, header=0)
    checi: dict[int, TrainService] = {}
    ts = None
    for idx, row in data.iterrows():
        if ts is None or ts.id != int(row['列车序号']):
            if ts is not None:
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
            ruler_info = run_ruler[(
                rid,
                int(tmp[0].strip('站')),
                int(tmp[1].strip('站'))
            )]
        except:
            ruler_info = None
        ts.path.append(
            TrainStation(
                id=int(row['车站名称'].strip('站')),
                ruler_info=ruler_info,
                stop_time_range=(int(sr[0]), int(sr[1])),
                stop_strategy=row['停站要求'],
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
