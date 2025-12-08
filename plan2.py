# %%
from dataloader import load

info = load()

checi = info['车次信息']
for tid, ts in checi.items():
    print('车次ID', tid, 
          '理想发车', ts.ideally_time_setoff,
          '理想到达', ts.ideally_time_achieve)

# %%
import heapq
import itertools
import random
from dataclasses import dataclass

@dataclass
class ResultRow:
    station_id: int = -1
    track: str = None
    setoff_time: int = 0
    achieve_time: int = 0

@dataclass
class TrainServiceState:
    prev_action_time: int = -999
    tid: int = -1
    station_rank: int = 0
    is_achieve: bool = False

def get_available_tracks(train_station_state, track_table, tid, sid) -> list[str] :
    res = []
    for track in track_table[(tid, sid)]:
        if train_station_state[sid][track] == -1:
            res.append(track)
    return res 

def get_exchange_time(tid, action_time, exchanges, res) -> int :
    next_ts_id = exchanges[tid][0]
    min_exchange_time = exchanges[tid][2] + action_time
    max_exchange_time = exchanges[tid][3] + action_time
    next_action_time = res[next_ts_id][0].setoff_time
    ###### 跨日班车 ######
    if checi[tid].ideally_time_achieve > checi[next_ts_id].ideally_time_setoff:
        next_action_time += 86400
        if next_action_time < min_exchange_time:
            next_action_time = min_exchange_time % 86400
        elif next_action_time > max_exchange_time:
            next_action_time = max_exchange_time % 86400
        else:
            next_action_time %= 86400
    ###### 一般情况 ######
    else:
        if next_action_time < min_exchange_time:
            next_action_time = min_exchange_time
        elif next_action_time > max_exchange_time:
            next_action_time = max_exchange_time
    return next_action_time
    # next_ts_id = exchanges[tid][0]
    # min_exchange_time = exchanges[tid][2]
    # max_exchange_time = exchanges[tid][3]
    # next_action_time = res[next_ts_id][0].setoff_time
    # time_gap = next_action_time - action_time
    # if time_gap < min_exchange_time or time_gap > max_exchange_time:
    #     # print("交路冲突！")
    #     # fail_set.append(tid)
    #     if time_gap < min_exchange_time:
    #         next_action_time = action_time + min_exchange_time
    #     else:
    #         next_action_time = action_time + max_exchange_time
    # return next_action_time

# 记录当前列车状态：（优先级）当前行动发生时间，（队列元素）（行动发生时间，车次，站次, 到达/始发）

# 记录当前车站状态：车站id -> 字典(股道id, 占用股道车次（-1表示无占用）)
track_table = info['车站股道']
train_station_state : dict[int, dict[str, int]] = {} 
for station_id, tracks in track_table.items():
    train_station_state[station_id] = {}
    for track in tracks:
        train_station_state[station_id][track] = -1
track_table = info['列车停站股道']


# 记录当前已安排车次信息: list[]
res = [[]]
for tid, ts in checi.items():
    start_station = ts.path[0].id
    setoff_time = ts.ideally_time_setoff
    achieve_time = -999
    res.append([ResultRow(station_id=start_station, track=None, setoff_time=setoff_time, achieve_time=achieve_time)])
    # train_station_state[start_station][0] += 1
    # if train_station_state[train_station][0] > train_station_state[start_station][1]:
    #     print("无法按照理想情况发车!")

# 记录交路信息
exchanges = info['交路信息']
next_of = {tid: exchanges[tid][0] for tid in exchanges}
rev_next = set(next_of.values())
heads = [tid for tid in checi.keys() if tid not in rev_next]
chains = []
visited = set()
for h in sorted(heads, key=lambda t: checi[t].ideally_time_setoff):
    chain = [h]
    visited.add(h)
    cur = h
    while cur in next_of and next_of[cur] not in visited:
        cur = next_of[cur]
        chain.append(cur)
        visited.add(cur)
    chains.append(chain)
for tid in checi.keys():
    if tid not in visited:
        chains.append([tid])
fail_set : list[int] = []
for chain in chains:
    priority_queue = []
    counter = itertools.count()
    chain_set = set(chain)
    head = chain[0]
    action_time = checi[head].ideally_time_setoff
    heapq.heappush(priority_queue, (action_time, next(counter), TrainServiceState(-999, head, 0, False)))
    while priority_queue:
        action_time, _, ts_state = heapq.heappop(priority_queue)
        prev_action_time = ts_state.prev_action_time
        tid = ts_state.tid
        ts = checi[tid]
        rank = ts_state.station_rank
        is_achieve = ts_state.is_achieve
        station = ts.path[rank]

    ###### 检查记录是否有效 ######
    ###### 检查方法：######
    ###### 情况一：始发车站。检查行动时间是否等于发车时间。######
    if rank == 0:
        if action_time != res[tid][0].setoff_time:
            continue
    ###### 情况二：非始发车站。核对上一行动时间 ######
    else:
        actual_prev_action_time = res[tid][-1].setoff_time if is_achieve else res[tid][-1].achieve_time
        if prev_action_time != actual_prev_action_time:
            continue

    if station.is_ideal_stop:
        ###### 处理终点站 ######
        if rank == len(ts.path) - 1:
            action_time += station.ruler_info.stop
            res[tid].append(ResultRow(station_id=station.id, track=None, setoff_time=-999, achieve_time=action_time))
            if tid not in exchanges:
                continue
            else:
                next_tid = exchanges[tid][0]
                if next_tid not in chain_set:
                    continue
                next_action_time = get_exchange_time(tid, action_time, exchanges, res)
                if next_action_time != res[next_tid][0].setoff_time:
                    heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(action_time, next_tid, 0, False)))
                    res[next_tid].clear()
                    start_station_next = checi[next_tid].path[0].id
                    res[next_tid].append(ResultRow(station_id=start_station_next, track=None, setoff_time=next_action_time, achieve_time=-999))
                available_tracks = get_available_tracks(train_station_state, track_table, tid, station.id)
                if len(available_tracks) == 0:
                    print("车站{}已满载，车次{}无法入站".format(station.id, tid))
                    fail_set.append(tid)
                    continue
                track = available_tracks[random.randint(0, len(available_tracks) - 1)]
                train_station_state[station.id][track] = tid
                res[tid][-1].track = track
                res[next_tid][0].track = track

        else:
            ###### 处理到站 ######
            if is_achieve:
                available_tracks = get_available_tracks(train_station_state, track_table, tid, station.id)
                if len(available_tracks) == 0:
                    print("车站{}已满载，车次{}无法入站".format(station.id, tid))
                    fail_set.append(tid)
                    continue
                track = available_tracks[random.randint(0, len(available_tracks) - 1)]
                train_station_state[station.id][track] = tid
                action_time += station.ruler_info.stop
                res[tid].append(ResultRow(station_id=station.id, track=track, setoff_time=-999, achieve_time=action_time))
                next_action_time = action_time + station.stop_time_range[0]
                heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(action_time, tid, rank, False)))

            ###### 处理离站 ######
            else:
                if rank == 0:
                    if res[tid][0].track == None:
                        available_tracks = get_available_tracks(train_station_state, track_table, tid, station.id)
                        if len(available_tracks) == 0:
                            min_modified_setoff_time = 86400
                            modified_track = -1
                            for track in track_table[(tid, station.id)]:
                                occupied_tid = train_station_state[station.id][track]
                                occupied_station_info = None
                                for _station in checi[occupied_tid].path:
                                    if _station.id == station.id:
                                        occupied_station_info = _station
                                        break
                                modified_setoff_time = res[exchanges[occupied_tid][0]][0].setoff_time + 1 if len(res[occupied_tid]) == len(checi[occupied_tid].path) else res[occupied_tid][-1].achieve_time + _station.stop_time_range[0]
                                if (modified_setoff_time < min_modified_setoff_time):
                                    modified_track = track
                                    min_modified_setoff_time = modified_setoff_time
                            res[tid][0].setoff_time = min_modified_setoff_time
                            heapq.heappush(priority_queue, (min_modified_setoff_time, next(counter), TrainServiceState(-999, tid, 0, False)))
                            break
                        track = available_tracks[random.randint(0, len(available_tracks) - 1)]
                        res[tid][rank].track = track
                    else:
                        track = res[tid][0].track
                        train_station_state[station.id][track] = -1
                else:
                    track = res[tid][rank].track
                    train_station_state[station.id][track] = -1
                r = ts.path[rank+1].ruler_info
                if r is not None:
                    res[tid][rank].setoff_time = action_time
                    next_action_time = action_time + r.runtime + r.start
                    heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(action_time, tid, rank + 1, True)))

    ####### 处理过站 ######          
    else:
        res[tid].append(ResultRow(station_id=station.id, track=None, setoff_time=action_time, achieve_time=action_time))
        r = ts.path[rank+1].ruler_info
        if r is not None:
            next_action_time = action_time + r.runtime
            heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(action_time, tid, rank + 1, True)))



# %%
sum = 0
for tid, ts in checi.items():
    if res[tid][-1].setoff_time != -999:
        continue
    ideally_time_setoff = ts.ideally_time_setoff 
    actual_time_setoff = res[tid][0].setoff_time % 86400
    ideally_time_achieve = ts.ideally_time_achieve
    actual_time_achieve = res[tid][-1].achieve_time % 86400
    print("车次：{}，出发时间偏移：{}，达到时间偏移：{}！".format(tid, actual_time_setoff - ideally_time_setoff, actual_time_achieve - ideally_time_achieve))
    sum += abs(actual_time_setoff - ideally_time_setoff) + abs(actual_time_achieve - ideally_time_achieve)

# %%
for tid, exchange in exchanges.items():
    prev_time = checi[tid].ideally_time_achieve
    next_time = checi[exchange[0]].ideally_time_setoff
    if prev_time > next_time:
        print("前车序号：{}，理想到达时间：{}，后车序号：{}，理想出发时间{}。".format(tid, prev_time, exchange[0], next_time))

# %%
res[109]

# %%
train : dict[int, list[int]] = {}
tail_tids : dict[int, int] = {}
for i, exchange in exchanges.items():
    prev_tid = i
    next_tid = exchange[0]
    if prev_tid in tail_tids:
        head_tid = tail_tids[prev_tid]
        train[head_tid].append(next_tid)
        tail_tids[next_tid] = head_tid
        tail_tids.pop(prev_tid)
    else:
        train[prev_tid] = [next_tid]
        tail_tids[next_tid] = prev_tid

# %%



