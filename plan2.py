# %% 代码分隔（Jupyter风格，表示一个单元开始）
# 从自定义数据加载器导入 load 函数，用于统一读取调度所需的全部结构化数据
from dataloader import load

# 读取所有信息：包含车次、站点、股道、进路、交路、间隔时间等字典/对象
info = load()

# 车次信息字典：tid -> 列车对象（包含路径、理想到/发时刻等）
checi = info['车次信息']
# 打印所有车次的理想发车/到达时刻，便于加载后快速检查
for tid, ts in checi.items():
    print('车次ID', tid, 
          '理想发车', ts.ideally_time_setoff,
          '理想到达', ts.ideally_time_achieve)

# %% 代码分隔（第二个单元）
# 导入标准库：
# - heapq：小根堆，实现按时间优先的事件队列
# - itertools：提供计数器等迭代工具
# - random：随机选择（当前策略中已基本不用）
# - dataclass：用于定义轻量数据结构
import heapq
import itertools
import random
from dataclasses import dataclass

BACKTRACK_ENABLED = True
BACKTRACK_MAX_DELAY = 1800
BACKTRACK_STEP = 60

# 每一条调度结果记录：某车次在某站的股道与到/发时刻（-999 表示该方向无含义）
@dataclass
class ResultRow:
    station_id: int = -1        # 站点ID
    track: str = None           # 股道ID（字符串）
    setoff_time: int = 0        # 发车时间（秒），-999 表示当前记录无发车
    achieve_time: int = 0       # 到达时间（秒），-999 表示当前记录无到达
    update_cnt: int = 0         # 版本计数，用于防止过期事件继续推进

# 事件的最小载体：进入堆的实体，描述将要处理的到/发/通过动作
@dataclass
class TrainServiceState:
    update_cnt: int = 0         # 与 res[tid][0].update_cnt 对齐，不匹配则视为过期
    eid: int = -999             # 进路事件ID（-999 表示普通到/发/通过事件）
    tid: int = -1               # 车次ID
    station_rank: int = 0       # 路径中的站序（0 为始发站）
    is_achieve: bool = False    # True 表示到达事件；False 表示离站/发车事件
    max_delay_time: int = 0     # 当前事件允许的最大延迟预算（秒）

def get_available_tracks(ts, rank, action_time, max_delay_time) -> list[(str, int, int, bool)] :
    # 给定列车、站序、目标时刻和延迟预算，枚举“在该站可用”的股道候选
    # 返回：列表[(track, 可执行时刻, 剩余延迟预算, 是否现在执行)]
    available_tracks = []
    tid = ts.id
    sid = ts.path[rank].id
    # 作业类型：如果不是始发站且上一条记录存在发车时间（说明刚到达过），则为“接车”，否则为“发车”
    worktype = '接车' if rank != 0 and res[tid][-1].setoff_time != -999 else '发车'
    # 遍历该车次在该站允许停靠的股道集合
    for track in track_table[(tid, sid)]:
        # 情况1：股道当前空闲（未被任何车占用）
        if train_station_state[sid][track][0] == -1:
            eid = get_entrance(ts, rank, track, worktype)  # 找到对应该动作的进路ID
            (_action_time, _max_delay_time, _action_now) = check_entrance(eid, action_time, max_delay_time)  # 检查进路可行性
            if _action_time != -999:
                available_tracks.append((track, _action_time, _max_delay_time, _action_now))
        # 情况2：股道被占用，但在延迟窗口内会释放，尝试以释放时刻为起点检查进路
        elif action_time < train_station_state[sid][track][1] and train_station_state[sid][track][1] < action_time + max_delay_time:
            eid = get_entrance(ts, rank, track, worktype)
            # 注意：此处使用 achieve_time 变量但未定义，推测应为“站占用释放后的剩余延迟预算修正”，保持原逻辑不改动，仅标注说明
            (_action_time, _max_delay_time, _action_now) = check_entrance(
                eid,
                train_station_state[sid][track][1],
                max_delay_time + achieve_time - train_station_state[sid][track][1]
            )
            if _action_time != -999:
                available_tracks.append((track, _action_time, _max_delay_time, _action_now))
    return available_tracks 

def get_exchange_time(tid, action_time) -> tuple[int,int] :
    # 计算交路衔接时后续车的开始时刻：在 [min, max] 窗口内对齐到最近的可行点
    next_ts_id = exchanges[tid][0]                  # 后续车次ID
    min_exchange_time = exchanges[tid][2] + action_time  # 交路最小连接时间
    max_exchange_time = exchanges[tid][3] + action_time  # 交路最大连接时间
    next_action_time = res[next_ts_id][0].setoff_time    # 后车当前计划的始发现有时刻
    max_delya_time = 0                                   # 占位变量（未使用），保留原样
    ###### 跨日班车 ######
    if checi[tid].ideally_time_achieve > checi[next_ts_id].ideally_time_setoff:
        next_action_time += 86400                        # 跨日对齐：后车理想发车早于前车理想到达，需加一天
        if next_action_time < min_exchange_time:
            next_action_time = min_exchange_time
        elif next_action_time > max_exchange_time:
            next_action_time = max_exchange_time 
    ###### 一般情况 ######
    else:
        if next_action_time < min_exchange_time:
            next_action_time = min_exchange_time
        elif next_action_time > max_exchange_time:
            next_action_time = max_exchange_time
    # 返回对齐到 86400 内的时刻，以及剩余延迟预算（窗口右端 - 对齐时刻）
    return (next_action_time % 86400, max_exchange_time - next_action_time)

def get_entrance(ts, rank, track, worktype) -> int:
    # 根据当前站、相邻站、股道与作业类型，查找对应的进路ID（若不存在返回 None）
    curr_sid = ts.path[rank].id 
    prev_sid = ts.path[rank-1].id if worktype in {'接车', '通过接车'} else ts.path[rank+1].id
    try: 
        entrance = info['进路信息'][(curr_sid, prev_sid, track, worktype)]
    except:
        entrance = None
    return entrance

def check_entrance(entrance, action_time, max_delay_time) -> tuple[int, int, bool]:
    # 检查单条进路在 action_time 时是否可用；若需要推迟到进路最早空闲，则在延迟预算内对齐
    if entrance_states[entrance][1] > action_time:             # 进路最早空闲时刻晚于当前动作时刻
        if entrance_states[entrance][1] > action_time + max_delay_time:  # 超出延迟预算则不可行
            return (-999, -999, False)
        else:
            _max_delay_time = max_delay_time - (entrance_states[entrance][1] - action_time)  # 剩余延迟预算
            _action_time = entrance_states[entrance][1]                                     # 对齐到进路空闲时刻
            return (_action_time, _max_delay_time, False)
    return (action_time, max_delay_time, True)                  # 无需等待，立刻可行

def check_pass_entrance(ts, rank, action_time, max_delay_time) -> tuple[int, int, bool]:
    # 检查“通过”场景：需要同时满足‘通过接车’与‘通过发车’两条进路的空闲时刻
    tid = ts.id
    sid = ts.path[rank].id
    track = info['列车通过股道'][(tid, sid)]
    achieve_entrance = get_entrance(ts, rank, track, '通过接车')
    setoff_entrance = get_entrance(ts, rank, track, '通过发车')
    min_feasible_time = max(entrance_states[achieve_entrance][1], entrance_states[setoff_entrance][1])
    if min_feasible_time > action_time:
        if min_feasible_time > action_time + max_delay_time:
            return (-999, -999, False)
        else:
            _max_delay_time = max_delay_time - (min_feasible_time - action_time)  # 两条进路共同约束下的剩余延迟
            _action_time = min_feasible_time                                     # 对齐到两者的最大值
            return (_action_time, _max_delay_time, False)
    return (action_time, max_delay_time, True)

def backtrack_check_entrance(eid, action_time, max_delay_time) -> tuple[int, int, bool]:
    if not BACKTRACK_ENABLED:
        return (-999, -999, False)
    delay = max_delay_time
    while delay <= BACKTRACK_MAX_DELAY:
        (_action_time, _max_delay_time, _action_now) = check_entrance(eid, action_time, delay)
        if _action_time != -999:
            return (_action_time, _max_delay_time, _action_now)
        delay += BACKTRACK_STEP
    return (-999, -999, False)

def backtrack_get_available_tracks(ts, rank, action_time, max_delay_time) -> list[(str, int, int, bool)]:
    if not BACKTRACK_ENABLED:
        return []
    delay = max_delay_time
    while delay <= BACKTRACK_MAX_DELAY:
        cands = get_available_tracks(ts, rank, action_time, delay)
        if len(cands) > 0:
            return cands
        delay += BACKTRACK_STEP
    return []

def backtrack_check_pass(ts, rank, action_time, max_delay_time) -> tuple[int, int, bool]:
    if not BACKTRACK_ENABLED:
        return (-999, -999, False)
    delay = max_delay_time
    while delay <= BACKTRACK_MAX_DELAY:
        (_action_time, _max_delay_time, _action_now) = check_pass_entrance(ts, rank, action_time, delay)
        if _action_time != -999:
            return (_action_time, _max_delay_time, _action_now)
        delay += BACKTRACK_STEP
    return (-999, -999, False)

def update_entrance_state(tid, eid, action_time, update_cnt):
    # 进路占用传播：根据“前后进路最小间隔”更新下游进路的最早空闲时刻，并将其解锁事件入堆
    if eid in time_gap_former_index:
        for _eid, _time_gap in time_gap_former_index[eid]:
            _next_action_time = action_time + _time_gap
            if entrance_states[_eid][1] < _next_action_time:
                entrance_states[_eid] = (tid, _next_action_time)
                # 将“进路解锁事件”压入堆，使用 eid 标识此为进路事件
                heapq.heappush(priority_queue, (_next_action_time, next(counter), TrainServiceState(update_cnt, _eid, tid, -1, True, 0)))

# 事件优先队列：记录“动作发生时刻”和事件体，按时间小根堆排序
# 说明：
# - 元组结构：(action_time, 顺序计数, TrainServiceState)
# - 顺序计数避免时间相同的比较冲突
priority_queue = []
counter = itertools.count()
# 初始化：为每个车次在其理想发车时刻创建一条“始发事件”并入堆
for tid, ts in checi.items():
    action_time = ts.ideally_time_setoff
    heapq.heappush(priority_queue, (action_time, next(counter), TrainServiceState(0, -999, tid, 0, False, 0)))

# 记录当前车站状态：站 -> 股道 -> (占用车次ID（-1表示空闲），预计解锁时间)
track_table = info['车站股道']
train_station_state : dict[int, dict[str, (int, int)]] = {} 
# 初始化所有站的股道占用为“空闲（-1）”，解锁时间为0
for station_id, tracks in track_table.items():
    train_station_state[station_id] = {}
    for track in tracks:
        train_station_state[station_id][track] = (-1, 0)
# 重载 track_table 为“列车在站可选股道字典”，键值通常为 (tid, sid) -> [track...]
track_table = info['列车停站股道']


# 记录当前已安排车次信息：res[tid] 为一个列表，保存该车在各站的结果行
res = [[]]
# 初始化每个车次的第一条记录：始发站、股道暂未选、理想发车时刻、到达置为-999、版本0
for tid, ts in checi.items():
    start_station = ts.path[0].id
    setoff_time = ts.ideally_time_setoff
    achieve_time = -999
    res.append([ResultRow(station_id=start_station, track=None, setoff_time=setoff_time, achieve_time=achieve_time, update_cnt=0)])

# 交路信息：tid -> (next_tid, ..., min_exchange, max_exchange)
exchanges = info['交路信息']

# 构建进路间隔索引：
# - former_index[eid] = [(next_eid, gap), ...]
# - latter_index[eid] = [(prev_eid, gap), ...]
time_gap_former_index : dict[int, list[(int, int)]] = {}
time_gap_latter_index : dict[int, list[(int, int)]] = {}
for (prev_eid, next_eid), time_gap in info['间隔时间'].items():
    if prev_eid not in time_gap_former_index:
        time_gap_former_index[prev_eid] = []
    time_gap_former_index[prev_eid].append((next_eid, time_gap))
    if next_eid not in time_gap_latter_index:
        time_gap_latter_index[next_eid] = []
    time_gap_latter_index[next_eid].append((prev_eid, time_gap))

# 进路信息字典：组合键 -> 进路ID
entrances = info['进路信息']

# 进路状态：eid -> (占用车次ID, 进路最早空闲时刻)
entrance_states : dict[int, (int, int)] = {}
for eid in entrances.values():
    entrance_states[eid] = (-1, -1)

# 调度失败的车次集合（发生不可化解冲突时记录）
fail_set : list[int] = []
# while priority_queue:

def process_event(priority_queue) -> bool:

    while priority_queue:
        # 取出最早可执行事件
        action_time, _, ts_state = heapq.heappop(priority_queue)
        update_cnt = ts_state.update_cnt         # 版本校验用
        eid = ts_state.eid                       # 进路事件ID（-999 表示普通事件）
        tid = ts_state.tid                       # 车次ID
        ts = checi[tid]                          # 车次对象
        rank = ts_state.station_rank             # 当前站序
        is_achieve = ts_state.is_achieve         # True：到达事件；False：离站/发车事件
        station = ts.path[rank]                  # 当前站对象
        sid = station.id                         # 当前站ID
        max_delay_time = ts_state.max_delay_time # 当前事件延迟预算

        ###### 检查记录是否有效 ######
        ###### 检查方法：校验 update_cnt ######
        # 若事件版本与该车结果表头版本不一致，说明此事件过期，直接丢弃
        if update_cnt != res[tid][0].update_cnt:
            continue
        
        ###### 检查是否为进路事件 ######
        # 进路事件仅用于在进路空闲时清理标记，不推动车次进度
        if eid != -999:
            _tid, _unlock_time = entrance_states[eid]
            if _tid != tid:
                continue        # 若占用标记不属于本车，忽略
            else:
                entrance_states[eid] = (-1, -1)  # 释放进路占用标记
            continue
        
        # 分两类处理：停车站（到/发）与通过站（不停车）
        if station.is_ideal_stop:
            ###### 处理始发站 ######
            if rank == 0:
                track = res[tid][0].track     # 若之前已选定股道则复用
                action_now = True            # 默认认为可立刻执行，后续检查可能改变
                if track == None:
                    # 首次选择始发股道：不允许延迟（延迟预算0），尝试按理想时刻发车
                    available_tracks = get_available_tracks(ts, rank, action_time, 0)
                    if len(available_tracks) == 0:
                        ##### 无法按理想时间发车，寻找最早的可行发车时间 ######
                        min_modified_setoff_time = 86400  # 从一天长度作为上界开始找最早可行时刻
                        modified_track = -1
                        for track in track_table[(tid, sid)]:
                            occupied_tid = train_station_state[sid][track][0]   # 当前占用的车次ID（或-1）
                            occupied_station_info = None
                            modified_setoff_time = 86400
                            if occupied_tid == -1:
                                # 股道空闲：由发车进路的最早空闲时刻决定可行时刻
                                eid = get_entrance(ts, rank, track, '发车')
                                modified_setoff_time = entrance_states[eid][1]
                            else:
                                # 找到占用车在该站的站信息，以便计算其最早离站时间
                                for _station in checi[occupied_tid].path:
                                    if _station.id == sid:
                                        occupied_station_info = _station
                                        break
                                if len(res[occupied_tid]) == len(checi[occupied_tid].path):
                                    # 若占用车已终到，则由交路后车的始发时刻决定空档；跨日则加一天
                                    modified_setoff_time = res[exchanges[occupied_tid][0]][0].setoff_time
                                    if modified_setoff_time < action_time:
                                        modified_setoff_time += 86400
                                else:
                                    # 否则由其到达后最小停站时间形成最早离站空档
                                    modified_setoff_time = res[occupied_tid][-1].achieve_time + occupied_station_info.stop_time_range[0]
                            if (modified_setoff_time < min_modified_setoff_time):
                                modified_track = track
                                min_modified_setoff_time = modified_setoff_time
                                # print("股道：{}，车次：{}，最早可用时间：{}".format(track, occupied_tid, min_modified_setoff_time))
                        # 改签发车时刻为“最早可行”，并将该事件重新入堆
                        res[tid][0].setoff_time = min_modified_setoff_time
                        heapq.heappush(priority_queue, (min_modified_setoff_time, next(counter), TrainServiceState(update_cnt, -999, tid, 0, False, 0)))
                        continue
                    # 始发选择策略：优先选择“后续进路影响更小”的股道（前向间隔数少）
                    # (track, action_time, max_delay_time, action_now) = available_tracks[random.randint(0, len(available_tracks) - 1)]
                    available_tracks.sort(key = lambda x: len(time_gap_former_index[get_entrance(ts, rank, x[0], '发车')]) if get_entrance(ts, rank, x[0], '发车') in time_gap_former_index else 0)
                    (track, action_time, max_delay_time, action_now) = available_tracks[0]
                    res[tid][rank].track = track
                else: 
                    # 若已有股道选择，先释放其站占用标记，再检查发车进路是否在延迟预算内可行
                    train_station_state[sid][track] = (-1, 0)
                    eid = get_entrance(ts, rank, track, '发车')
                    if eid == None:
                        print("DO NOT FIND ENTRANCE!（发车）")
                        break
                    (action_time, max_delay_time, action_now) = check_entrance(eid, action_time, max_delay_time)
                    if action_time == -999:
                        (_action_time, _max_delay_time, _action_now) = backtrack_check_entrance(eid, action_time, max_delay_time)
                        if _action_time == -999:
                            print("交路冲突（始发站）：站次{}，车次{}".format(sid, tid))
                            fail_set.append(tid)
                            continue
                        action_time, max_delay_time, action_now = _action_time, _max_delay_time, _action_now

                # 根据是否需要等待，决定入堆或执行并推进至下一站到达
                if not action_now:
                    heapq.heappush(priority_queue, (action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank, False, max_delay_time)))
                else:
                    update_entrance_state(tid, eid, action_time, update_cnt)
                    r = ts.path[rank+1].ruler_info
                    if r is not None:
                        res[tid][rank].setoff_time = action_time
                        next_action_time = action_time + r.runtime + r.start
                        if ts.path[rank + 1].is_ideal_stop:
                            next_action_time += r.stop
                        heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank + 1, True, 120)))

            ###### 处理终点站 ######
            elif rank == len(ts.path) - 1:
                # 终到站：在允许延迟预算内选择最早可接车的股道
                available_tracks = get_available_tracks(ts, rank, action_time, max_delay_time)
                if len(available_tracks) == 0:
                    bt_tracks = backtrack_get_available_tracks(ts, rank, action_time, max_delay_time)
                    if len(bt_tracks) == 0:
                        print("交路冲突（终点站）：车次{}，站次{}".format(sid, tid))
                        fail_set.append(tid)
                        continue
                    available_tracks = bt_tracks
                # 选择“最早可行时刻”的股道
                # (track, action_time, max_delay_time, action_now) = available_tracks[random.randint(0, len(available_tracks) - 1)]
                available_tracks.sort(key = lambda x: x[1])
                (track, action_time, max_delay_time, action_now) = available_tracks[0]
                if not action_now:
                    heapq.heappush(priority_queue, (action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank, True, max_delay_time)))
                else:
                    # 记录接车进路占用影响，并写入终到结果行
                    eid = get_entrance(ts, rank, track, '接车')
                    update_entrance_state(tid, eid, action_time, update_cnt)
                    res[tid].append(ResultRow(station_id=sid, track=track, setoff_time=-999, achieve_time=action_time, update_cnt=update_cnt))
                    # 若存在交路，将后车的“始发事件”按交路窗口对齐并入堆；同时在同股道上设置接续占用
                    if tid not in exchanges:
                        continue
                    else:
                        next_tid = exchanges[tid][0]
                        (next_action_time, max_delay_time) = get_exchange_time(tid, action_time)
                        # if next_action_time != res[next_tid][0].setoff_time:
                        heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(update_cnt + 1, -999, next_tid, 0, False, max_delay_time)))
                        res[next_tid].clear()
                        res[next_tid].append(ResultRow(station_id=sid, track=track, setoff_time=next_action_time, achieve_time=-999, update_cnt=update_cnt+1))
                        
                        train_station_state[sid][track] = (tid, next_action_time)
                        res[tid][-1].track = track
                        res[next_tid][0].track = track

            else:
                ###### 处理中间站：先到站后离站 ######
                if is_achieve:
                    # 到站：固定允许延迟窗口为 120 秒，选择最早可接车股道
                    available_tracks = get_available_tracks(ts, rank, action_time, 120)
                    if len(available_tracks) == 0:
                        bt_tracks = backtrack_get_available_tracks(ts, rank, action_time, 120)
                        if len(bt_tracks) == 0:
                            print("交路冲突（到站）：车次{}，站次{}".format(sid, tid))
                            fail_set.append(tid)
                            continue
                        available_tracks = bt_tracks
                    ##### TODO: DESIGN STRATEGIES TO SELECT TRACK. #####
                    # 选择最早可行股道
                    # (track, action_time, max_delay_time, action_now) = available_tracks[random.randint(0, len(available_tracks) - 1)]
                    available_tracks.sort(key = lambda x: x[1])
                    (track, action_time, max_delay_time, action_now) = available_tracks[0]
                    if not action_now:
                        heapq.heappush(priority_queue, (action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank, True, max_delay_time)))
                    else:
                        # 记录接车进路占用与到达结果，并将“离站事件”按最小停站时间入堆，同时设置股道占用到该离站时刻
                        eid = get_entrance(ts, rank, track, '接车')
                        update_entrance_state(tid, eid, action_time, update_cnt)
                        res[tid].append(ResultRow(station_id=sid, track=track, setoff_time=-999, achieve_time=action_time, update_cnt=update_cnt))
                        next_action_time = action_time + station.stop_time_range[0]
                        heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank, False, station.stop_time_range[1]-station.stop_time_range[0])))
                        train_station_state[sid][track] = (tid, next_action_time)

                ###### 处理离站 ######
                else: 
                    # 离站/发车：释放股道占用，检查发车进路可行，成功则推进到下一站到达
                    track = res[tid][rank].track
                    train_station_state[sid][track] = (-1, 0)
                    eid = get_entrance(ts, rank, track, '发车')
                    if eid == None:
                        print("DO NOT FIND ENTRANCE!（发车）")
                        break
                    (action_time, max_delay_time, action_now) = check_entrance(eid, action_time, max_delay_time)
                    if action_time == -999:
                        (_action_time, _max_delay_time, _action_now) = backtrack_check_entrance(eid, action_time, max_delay_time)
                        if _action_time == -999:
                            # print("交路冲突（发车）：站次{}，车次{}".format(sid, tid))
                            # fail_set.append(tid)
                            # continue
                            # TODO 加回溯搜索！！！
                            #
                            '''
                            回溯 返回 res[tid][rank-1]回退上一个站
                            1. 上一个站停车：
                                退回上一个站的进站时间，重新选择停站和出站方案
                                    - 重新选择股道
                                    - 重新选择到站时间，出站时间

                            怎么回退？
                            删除res中所有发生时间晚于回退时间点的记录
                            根据删除后的res重新构造priority_queue（页重新构造TrainStationState， EntranceState）


                            x 2. 上一站没有停车：
                            
                            '''

                        action_time, max_delay_time, action_now = _action_time, _max_delay_time, _action_now
                    if not action_now:
                        heapq.heappush(priority_queue, (action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank, False, max_delay_time)))
                    else:
                        update_entrance_state(tid, eid, action_time, update_cnt)
                        r = ts.path[rank+1].ruler_info
                        if r is not None:
                            res[tid][rank].setoff_time = action_time
                            next_action_time = action_time + r.runtime + r.start
                            if ts.path[rank + 1].is_ideal_stop:
                                next_action_time += r.stop
                            heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank + 1, True, 120)))

        ####### 处理过站 ######          
        else:
            # 通过站：不停车，需同时满足两条通过进路的空闲时刻
            track = info['列车通过股道'][(tid, sid)]
            (action_time, max_delay_time, action_now)= check_pass_entrance(ts, rank, action_time, max_delay_time)
            if action_time == -999:
                (_action_time, _max_delay_time, _action_now) = backtrack_check_pass(ts, rank, action_time, max_delay_time)
                if _action_time == -999:
                    print("交路冲突（通过接车/发车）：站次{}，车次{}".format(sid, tid))
                    fail_set.append(tid)
                    continue
                action_time, max_delay_time, action_now = _action_time, _max_delay_time, _action_now
            if not action_now:
                heapq.heappush(priority_queue, (action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank, True, max_delay_time)))
            else:
                # 两条进路均占用与传播，并在同一时刻记录到达与发出
                eid1 = get_entrance(ts, rank, track, '通过接车')
                update_entrance_state(tid, eid1, action_time, update_cnt)
                eid2 = get_entrance(ts, rank, track, '通过发车')
                update_entrance_state(tid, eid2, action_time, update_cnt)
                res[tid].append(ResultRow(station_id=sid, track=track, setoff_time=action_time, achieve_time=action_time, update_cnt=update_cnt))
                r = ts.path[rank+1].ruler_info
                if r is not None:
                    next_action_time = action_time + r.runtime
                    if ts.path[rank+1].is_ideal_stop:
                        next_action_time += r.stop
                    heapq.heappush(priority_queue, (next_action_time, next(counter), TrainServiceState(update_cnt, -999, tid, rank + 1, True, 120)))

    return True



# %% 调度结束后的统计输出单元
print(len(fail_set))                 # 输出失败车次数
sum = 0                              # 总偏移量（出发偏移 + 到达偏移）累加
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

# %% 交路理想到/发的跨日检查单元
for tid, exchange in exchanges.items():
    prev_time = checi[tid].ideally_time_achieve
    next_time = checi[exchange[0]].ideally_time_setoff
    if prev_time > next_time:
        print("前车序号：{}，理想到达时间：{}，后车序号：{}，理想出发时间{}。".format(tid, prev_time, exchange[0], next_time))

# %% 交路链路构建（将交路串成链）
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

# %% 股道时间线聚合：按 (sid, track) 汇总各列车的到/发时刻，并排序
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
    _r.sort(key = lambda x: max(x[1], x[2]))   # 按该车在该股道的“最早发生时刻（到或发）”排序


# 调度主循环结束后，若失败集合为空，则打印最终排班结果
if not fail_set:
    print("================ 调度成功！最终排班如下 ================")
    for tid, rows in enumerate(res):
        if not rows:          # 跳过空列表（res[0] 占位）
            continue
        print(f"车次 {tid}:")
        for r in rows:
            print(f"  站 {r.station_id} | 股道 {r.track} | 到达 {r.achieve_time if r.achieve_time != -999 else '—'} | 发车 {r.setoff_time if r.setoff_time != -999 else '—'}")
else:
    print("================ 调度失败！以下车次无法安排 ================")
    print(f"失败车次列表({len(fail_set)}):", fail_set)

在TODO和注释处根据注释，设置回溯搜索
回溯 返回 res[tid][rank-1]回退上一个站
                            1. 上一个站停车：
                                退回上一个站的进站时间，重新选择停站和出站方案
                                    - 重新选择股道
                                    - 重新选择到站时间，出站时间

                            怎么回退？
                            删除res中所有发生时间晚于回退时间点的记录
                            根据删除后的res重新构造priority_queue（页重新构造TrainStationState， EntranceState）


                            x 2. 上一站没有停车：
