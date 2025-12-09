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
    update_cnt: int = 0

@dataclass
class TrainServiceState:
    update_cnt: int = 0
    eid: int = -999
    tid: int = -1
    station_rank: int = 0
    is_achieve: bool = False

def get_available_tracks(tid, sid, action_time, max_slow_time) -> list[tuple[str, int]]:
    res = []
    for track in track_table[(tid, sid)]:
        if train_station_state[sid][track][0] == -1:
            res.append((track, action_time))
        elif action_time < train_station_state[sid][track][1] and train_station_state[sid][track][1] < action_time + max_slow_time:
            res.append((track, train_station_state[sid][track][1]))
    return res 

def get_exchange_time(tid, action_time) -> int:
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

def get_entrance(ts, rank, track, worktype) -> int:
    curr_sid = ts.path[rank].id 
    prev_sid = ts.path[rank-1].id if worktype in {'接车', '通过接车'} else ts.path[rank+1].id
    try: 
        entrance = info['进路信息'][(curr_sid, prev_sid, track, worktype)]
    except:
        entrance = None
    return entrance

def check_entrance(entrance, action_time, max_slow_time) -> tuple[int, int]:
    if entrance_states[entrance][1] > action_time:
        if entrance_states[entrance][1] > action_time + max_slow_time:
            return (-999, -999)
        else:
            max_slow_time -= (entrance_states[entrance][1] - action_time)
            action_time = entrance_states[entrance][1]
    return (action_time, max_slow_time)

def update_entrance_state(tid, eid, action_time, update_cnt):
    if eid in time_gap_former_index:
        for _eid, _time_gap in time_gap_former_index[eid]:
            _next_action_time = action_time + _time_gap
            if entrance_states[_eid][1] < _next_action_time:
                entrance_states[_eid] = (tid, _next_action_time)
                heapq.heappush(priority_queue, (_next_action_time, next(counter), TrainServiceState(update_cnt, _eid, tid, -1, True)))

# 记录当前列车状态：（优先级）当前行动发生时间，（队列元素）（行动发生时间，车次，站次, 到达/始发）
exchanges = info['交路信息']
classes = []
prev_of = {}
for _prev_tid, ex in exchanges.items():
    prev_of[ex[0]] = _prev_tid
heads = []
for tid in checi.keys():
    if tid not in prev_of:
        heads.append(tid)
for head in sorted(heads, key=lambda t: checi[t].ideally_time_setoff):
    seq = [head]
    _curr = head
    while _curr in exchanges:
        _next = exchanges[_curr][0]
        if _next in seq:
            break
        seq.append(_next)
        _curr = _next
    classes.append(seq)


# 记录当前车站状态：车站id -> 字典[股道id -> (占用股道车次（-1表示无占用），预计解锁时间)]
track_table = info['车站股道']
train_station_state : dict[int, dict[str, tuple[int, int]]] = {} 
for station_id, tracks in track_table.items():
    train_station_state[station_id] = {}
    for track in tracks:
        train_station_state[station_id][track] = (-1, 0)
track_table = info['列车停站股道']


# 记录当前已安排车次信息: list[]
res = [[]]
for tid, ts in checi.items():
    start_station = ts.path[0].id
    setoff_time = ts.ideally_time_setoff
    achieve_time = -999
    res.append([ResultRow(station_id=start_station, track=None, setoff_time=setoff_time, achieve_time=achieve_time, update_cnt=0)])

# 记录交路信息
exchanges = info['交路信息']

# 分别以前后车进路序号为键构建最小间隔时间字典
time_gap_former_index : dict[int, list[tuple[int, int]]] = {}
time_gap_latter_index : dict[int, list[tuple[int, int]]] = {}
for (prev_eid, next_eid), time_gap in info['间隔时间'].items():
    if prev_eid not in time_gap_former_index:
        time_gap_former_index[prev_eid] = []
    time_gap_former_index[prev_eid].append((next_eid, time_gap))
    if next_eid not in time_gap_latter_index:
        time_gap_latter_index[next_eid] = []
    time_gap_latter_index[next_eid].append((prev_eid, time_gap))

# 记录进路信息
entrances = info['进路信息']

# 记录进路状态
entrance_states : dict[int, tuple[int, int]] = {}
for eid in entrances.values():
    entrance_states[eid] = (-1, -1)

fail_set : list[int] = []
for seq in classes:
    priority_queue = []
    counter = itertools.count()
    first_tid = seq[0]
    action_time = checi[first_tid].ideally_time_setoff
    heapq.heappush(priority_queue, (action_time, next(counter), TrainServiceState(0, -999, first_tid, 0, False)))
    while priority_queue:
        action_time, _, ts_state = heapq.heappop(priority_queue)
        update_cnt = ts_state.update_cnt
        eid = ts_state.eid
        tid = ts_state.tid
        ts = checi[tid]
        rank = ts_state.station_rank
        is_achieve = ts_state.is_achieve
        station = ts.path[rank]
        sid = station.id

        ###### 检查记录是否有效 ######
        ###### 检查方法：校验 update_cnt ######
        if update_cnt != res[tid][0].update_cnt:
            continue

        ###### 检查是否为进路事件 ######
        if eid != -999:
            _tid, _unlock_time = entrance_states[eid]
            if _tid != tid:
                continue
            else:
                entrance_states[eid] = (-1, -1)
            continue

        if station.is_ideal_stop:
            ###### 处理终点站 ######
            if rank == len(ts.path) - 1:
                track = '-999'
                action_time += station.ruler_info.stop
                available_tracks = get_available_tracks(tid, sid, action_time, 120)
                if len(available_tracks) == 0:
                    print("车站{}已满载，车次{}无法入站".format(sid, tid))
                    fail_set.append(tid)
                    continue
                # (track, action_time) = available_tracks[random.randint(0, len(available_tracks) - 1)]

                for (_track, _action_time) in available_tracks:
                    eid = get_entrance(ts, rank, _track, '接车')
                    if eid == None:
                        print("DO NOT FIND ENTRANCE!（接车）")
                        break
                    (_action_time, _) = check_entrance(eid, _action_time, 0)
                    if _action_time == -999:
                        continue
                    else:
                        track = _track
                        action_time = _action_time
                        update_entrance_state(tid, eid, action_time, update_cnt)
                        break
                if track == '-999':
                    fail_set.append(tid)
                    continue

                res[tid].append(ResultRow(station_id=sid, track=None, setoff_time=-999, achieve_time=action_time, update_cnt=update_cnt))
                if tid not in exchanges:
                    continue
                else:
                    next_tid = exchanges[tid][0]
                    next_action_time = get_exchange_time(tid, action_time)
                    if next_action_time != res[next_tid][0].setoff_time:
                        heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(update_cnt + 1, -999, next_tid, 0, False)))
                        res[next_tid].clear()
                        res[next_tid].append(ResultRow(station_id=start_station, track=None, setoff_time=next_action_time, achieve_time=-999, update_cnt=update_cnt+1))
                    train_station_state[sid][track] = (tid, next_action_time)
                    res[tid][-1].track = track
                    res[next_tid][0].track = track

            else:
                ###### 处理到站 ######
                if is_achieve:
                    action_time += station.ruler_info.stop
                    available_tracks = get_available_tracks(tid, sid, action_time, 120)
                    if len(available_tracks) == 0:
                        print("车站{}已满载，车次{}无法入站".format(sid, tid))
                        fail_set.append(tid)
                        continue
                    ##### TODO: DESIGN STRATEGIES TO SELECT TRACK. #####
                    # (track, action_time) = available_tracks[random.randint(0, len(available_tracks) - 1)]
                    track = '-999'
                    for (_track, _action_time) in available_tracks:
                        eid = get_entrance(ts, rank, _track, '接车')
                        if eid == None:
                            print("DO NOT FIND ENTRANCE!（接车）")
                            break
                        (_action_time, _max_slow_time) = check_entrance(eid, _action_time, 0)
                        if _action_time == -999:
                            continue
                        else:
                            track = _track
                            action_time = _action_time
                            update_entrance_state(tid, eid, action_time, update_cnt)
                            break
                    if track == '-999':
                        fail_set.append(tid)
                        continue

                    res[tid].append(ResultRow(station_id=sid, track=track, setoff_time=-999, achieve_time=action_time, update_cnt=update_cnt))
                    next_action_time = action_time + station.stop_time_range[0]
                    heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank, False)))
                    train_station_state[sid][track] = (tid, next_action_time)

                ###### 处理离站 ######
                else:
                    ###### 处理始发站 ######
                    if rank == 0:
                        if res[tid][0].track == None:
                            available_tracks = get_available_tracks(tid, sid, action_time, 0)
                            if len(available_tracks) == 0:
                                print("车次{}无法按理想情况发车！".format(tid))
                                ##### 处理冲突：找到最早的可行发车时间 ######
                                min_modified_setoff_time = 86400
                                modified_track = -1
                                for track in track_table[(tid, sid)]:
                                    occupied_tid = train_station_state[sid][track][0]
                                    occupied_station_info = None
                                    for _station in checi[occupied_tid].path:
                                        if _station.id == sid:
                                            occupied_station_info = _station
                                            break
                                    modified_setoff_time = res[exchanges[occupied_tid][0]][0].setoff_time + 1 if len(res[occupied_tid]) == len(checi[occupied_tid].path) else res[occupied_tid][-1].achieve_time + _station.stop_time_range[0]
                                    if (modified_setoff_time < min_modified_setoff_time):
                                        modified_track = track
                                        min_modified_setoff_time = modified_setoff_time
                                        print("股道：{}，车次：{}，最早可用时间：{}".format(track, occupied_tid, min_modified_setoff_time))
                                res[tid][0].setoff_time = min_modified_setoff_time
                                heapq.heappush(priority_queue, (min_modified_setoff_time, next(counter), TrainServiceState(update_cnt, -999, tid, 0, False)))
                                break
                                # fail_set.append(tid)
                                # continue
                            (track, action_time) = available_tracks[random.randint(0, len(available_tracks) - 1)]
                            res[tid][rank].track = track
                        else:
                            track = res[tid][0].track
                            train_station_state[sid][track] = (-1, 0)
                    else:
                        track = res[tid][rank].track
                        train_station_state[sid][track] = (-1, 0)

                    eid = get_entrance(ts, rank, track, '发车')
                    if eid == None:
                        print("DO NOT FIND ENTRANCE!（发车）")
                        break
                    max_slow_time = station.stop_time_range[1] - station.stop_time_range[0]
                    (action_time, max_slow_time) = check_entrance(eid, action_time, max_slow_time)
                    if action_time == -999:
                        fail_set.append(tid)
                        continue
                    else:
                        update_entrance_state(tid, eid, action_time, update_cnt)

                    r = ts.path[rank+1].ruler_info
                    if r is not None:
                        res[tid][rank].setoff_time = action_time
                        next_action_time = action_time + r.runtime + r.start
                        heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank + 1, True)))

        ####### 处理过站 ######          
        else:
            track = info['列车通过股道'][(tid, sid)]
            max_slow_time = 120

            eid = get_entrance(ts, rank, track, '通过接车')
            if eid == None:
                print("DO NOT FIND ENTRANCE! (通过接车)")
                break
            (action_time, max_slow_time) = check_entrance(eid, action_time, max_slow_time)
            if action_time == -999:
                fail_set.append(tid)
                continue
            else:
                update_entrance_state(tid, eid, action_time, update_cnt)

            eid = get_entrance(ts, rank, track, '通过发车')
            if eid == None:
                print("DO NOT FIND ENTRANCE! （通过发车）")
                break
            (action_time, max_slow_time) = check_entrance(eid, action_time, max_slow_time)
            if action_time == -999:
                fail_set.append(tid)
                continue
            else:
                update_entrance_state(tid, eid, action_time, update_cnt)

            res[tid].append(ResultRow(station_id=sid, track=track, setoff_time=action_time, achieve_time=action_time, update_cnt=update_cnt))
            r = ts.path[rank+1].ruler_info
            if r is not None:
                next_action_time = action_time + r.runtime
                heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank + 1, True)))


# %%
print(len(fail_set))
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
print(sum)

# %%
for tid, exchange in exchanges.items():
    prev_time = checi[tid].ideally_time_achieve
    next_time = checi[exchange[0]].ideally_time_setoff
    if prev_time > next_time:
        print("前车序号：{}，理想到达时间：{}，后车序号：{}，理想出发时间{}。".format(tid, prev_time, exchange[0], next_time))

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
track_res : dict[(int, str), list[(int, int, int)]] = {}
for i in range(1, len(res)):
    tid = i
    for row in res[i]:
        sid = row.station_id
        track = row.track
        if track == None:
            track = info['列车通过股道'][(tid, sid)]
        setoff_time = row.setoff_time
        achieve_time = row.achieve_time
        if (sid, track) not in track_res:
            track_res[(sid, track)] = []
        track_res[(sid, track)].append((tid, achieve_time, setoff_time))

for _, _r in track_res.items():
    _r.sort(key = lambda x: max(x[1], x[2]))


# %%
station

# %%
res[120]

# %%
ts.path

# %%
track_table[(120,481)]

# %%
entrances[(481, 2779, 'VII', '发车')]

# %%



