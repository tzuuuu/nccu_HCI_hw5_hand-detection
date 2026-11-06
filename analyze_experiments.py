"""Validate and summarize the three collected HW5 sessions without changing inputs."""

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median, stdev

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from analyze_results import build_report
from interaction import point_to_zone
from reader_ui import COMMANDS, COMMAND_LABELS

BASE = Path(__file__).resolve().parent
OUT = BASE / 'results' / 'analysis'
SOURCES = (
    'experiment1_20261106-211554-402383.csv',
    'experiment2_20261106-211944-097386.csv',
    'experiment3_20261106-212231-247232.csv',
)


def stats(rows):
    correct = [r for r in rows if r['correct'] == 'true']
    times = [float(r['trigger_time_ms']) for r in correct]
    return dict(n=len(rows), correct=len(correct), success_rate=len(correct) / len(rows),
                false_trigger=sum(r['false_trigger'] == 'true' for r in rows),
                missed_trigger=sum(r['missed_trigger'] == 'true' for r in rows),
                detection_failure=sum(r['detection_failure'] == 'true' for r in rows),
                mean_ms=mean(times) if times else None, median_ms=median(times) if times else None,
                sd_ms=stdev(times) if len(times) > 1 else None,
                min_ms=min(times) if times else None, max_ms=max(times) if times else None,
                mean_fps=mean(float(r['mean_fps']) for r in rows),
                total_frames=sum(int(r['total_frames']) for r in rows),
                no_hand_frames=sum(int(r['no_hand_frames']) for r in rows),
                tracking_loss_count=sum(int(r['tracking_loss_count']) for r in rows),
                multi_hand_frames=sum(int(r['multi_hand_frames']) for r in rows))


def validate(sessions, paths):
    checks = []
    def check(name, condition):
        if not condition:
            raise ValueError('資料驗證失敗：' + name)
        checks.append(name)
    all_rows = [r for rows in sessions for r in rows]
    check('總筆數為 75，三組各 30/27/18', list(map(len, sessions)) == [30, 27, 18])
    ids = [(r['session_id'], r['trial_id']) for r in all_rows]
    check('無重複 session/trial', len(set(ids)) == len(ids))
    expected = [Counter({z: 5 for z in COMMANDS}),
                Counter({(z, level): 3 for z in ['Z1', 'Z2', 'Z3'] for level in ['Short', 'Medium', 'Long']}),
                Counter({(z, light): 3 for z in ['Z1', 'Z2', 'Z3'] for light in ['Normal Lighting', 'Dim Lighting']})]
    actual = [Counter(r['target_zone'] for r in sessions[0]),
              Counter((r['target_zone'], r['dwell_level']) for r in sessions[1]),
              Counter((r['target_zone'], r['lighting']) for r in sessions[2])]
    check('各區域、條件與重複次數完整', actual == expected)
    for i, rows in enumerate(sessions, 1):
        check('實驗 {} 的識別碼與流水號完整'.format(i),
              {r['experiment'] for r in rows} == {'experiment' + str(i)} and
              {r['trial_id'] for r in rows} == {'E{}-{:03d}'.format(i, n) for n in range(1, len(rows) + 1)} and
              len({r['session_id'] for r in rows}) == 1)
    for key, value in [('cooldown_seconds', '1.0'), ('detection_confidence', '0.5'),
                       ('presence_confidence', '0.5'), ('tracking_confidence', '0.5'),
                       ('mediapipe_version', '0.10.35'), ('timeout_seconds', '8')]:
        check(key + ' 固定', {r[key] for r in all_rows} == {value})
    model_hash = hashlib.sha256((BASE / 'models' / 'hand_landmarker.task').read_bytes()).hexdigest()
    check('同一模型，且與本機模型 SHA256 相符', {r['model_sha256'] for r in all_rows} == {model_hash})
    check('實驗一與三 baseline K=6', {r['dwell_frames'] for r in sessions[0] + sessions[2]} == {'6'})
    check('實驗一與二為正常光線', {r['lighting'] for r in sessions[0] + sessions[1]} == {'Normal Lighting'})
    check('實驗二 Short/Medium/Long 為 K=3/6/10', all(int(r['dwell_frames']) == {'Short': 3, 'Medium': 6, 'Long': 10}[r['dwell_level']] for r in sessions[1]))
    check('指令映射、布林結果與觸發時間一致', all(
        r['target_command'] == COMMAND_LABELS[COMMANDS[r['target_zone']]] and
        r['triggered_command'] == COMMAND_LABELS[COMMANDS[r['triggered_zone']]] and
        (r['correct'] == 'true') == (r['target_zone'] == r['triggered_zone']) and
        r['hand_detected'] == 'true' and r['false_trigger'] == r['missed_trigger'] == r['detection_failure'] == 'false' and
        math.isfinite(float(r['trigger_time_ms'])) and 0 < float(r['trigger_time_ms']) < 8000
        for r in all_rows))
    check('手腕座標落在記錄之觸發區域', all(point_to_zone(float(r['wrist_x']), float(r['wrist_y'])) == r['detected_zone'] == r['triggered_zone'] for r in all_rows))
    check('影格計數合理', all(int(r['total_frames']) >= int(r['dwell_frames']) and 0 <= int(r['no_hand_frames']) + int(r['multi_hand_frames']) <= int(r['total_frames']) for r in all_rows))
    deltas = [abs((datetime.fromisoformat(r['completed_at']) - datetime.fromisoformat(r['started_at'])).total_seconds() * 1000 - float(r['trigger_time_ms'])) for r in all_rows]
    check('起訖時間與 monotonic 觸發時間差異小於 50 ms', max(deltas) < 50)
    return dict(status='passed', checks=checks, total_trials=len(all_rows),
                sources=[dict(path=str(p.relative_to(BASE)), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths],
                model_sha256=model_hash, max_timestamp_discrepancy_ms=max(deltas))


def figure(rows, key, values, labels, title, filename):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, ax = plt.subplots(figsize=(9, 5.2), constrained_layout=True)
    colors = {'Z1': '#2563eb', 'Z2': '#16a085', 'Z3': '#d97706', 'Z4': '#9333ea', 'Z5': '#dc2626', 'Z6': '#475569'}
    seen = set()
    for i, value in enumerate(values):
        subset = [r for r in rows if r[key] == value and r['correct'] == 'true']
        for j, row in enumerate(subset):
            zone = row['target_zone']
            ax.scatter(i + (j - (len(subset) - 1) / 2) * .035, float(row['trigger_time_ms']) / 1000,
                       c=colors[zone], s=45, alpha=.8, edgecolors='white', linewidth=.5,
                       label=zone if zone not in seen else None)
            seen.add(zone)
        times = [float(r['trigger_time_ms']) / 1000 for r in subset]
        avg = mean(times)
        ax.plot([i - .27, i + .27], [avg, avg], c='#111827', lw=2.5, label='Mean' if i == 0 else None)
        ax.plot([i - .27, i + .27], [median(times), median(times)], c='#64748b', lw=1.5, ls='--', label='Median' if i == 0 else None)
        ax.text(i, 6.75, '{:.2f} s mean\nn={}; 100% success'.format(avg, len(subset)), ha='center', va='top', fontsize=9)
    ax.set_xticks(range(len(values)), labels)
    ax.set_ylim(0, 7.1)
    ax.set_ylabel('Trigger time from trial start (seconds)')
    ax.set_title(title, loc='left', weight='bold', pad=14)
    ax.grid(axis='y', alpha=.15)
    ax.set_axisbelow(True)
    ax.legend(loc='upper left', ncol=4, fontsize=8, bbox_to_anchor=(0, -.12), frameon=False)
    for suffix in ('png', 'svg'):
        fig.savefig(OUT / (filename + '.' + suffix), dpi=180, bbox_inches='tight')
    plt.close(fig)


def table(groups):
    lines = ['| 條件 | 次數 | 正確率 | 平均（ms） | 中位數（ms） | 標準差（ms） | 範圍（ms） |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for name, rows in groups:
        s = stats(rows)
        lines.append('| {} | {} | {:.1%} | {:.1f} | {:.1f} | {:.1f} | {:.1f}–{:.1f} |'.format(
            name, s['n'], s['success_rate'], s['mean_ms'], s['median_ms'], s['sd_ms'], s['min_ms'], s['max_ms']))
    return '\n'.join(lines)


def main():
    paths = [BASE / 'results' / name for name in SOURCES]
    sessions = [list(csv.DictReader(p.open(encoding='utf-8-sig', newline=''))) for p in paths]
    validation = validate(sessions, paths)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    all_rows = sum(sessions, [])
    groups = [('全部', all_rows)] + [('實驗' + str(i), rows) for i, rows in enumerate(sessions, 1)]
    groups += [('實驗一 ' + zone, [r for r in sessions[0] if r['target_zone'] == zone]) for zone in COMMANDS]
    groups += [('實驗二 ' + level, [r for r in sessions[1] if r['dwell_level'] == level]) for level in ('Short', 'Medium', 'Long')]
    groups += [('實驗三 ' + light, [r for r in sessions[2] if r['lighting'] == light]) for light in ('Normal Lighting', 'Dim Lighting')]
    fields = ['group'] + list(stats(all_rows))
    with (OUT / 'summary_metrics.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(dict(group=name, **stats(rows)) for name, rows in groups)
    (OUT / 'basic_summary.md').write_text(build_report(paths), encoding='utf-8')
    figure(sessions[0], 'target_zone', list(COMMANDS), list(COMMANDS), 'Experiment 1: six-command performance', '01_basic_accuracy')
    figure(sessions[1], 'dwell_level', ['Short', 'Medium', 'Long'], ['Short (K=3)', 'Medium (K=6)', 'Long (K=10)'], 'Experiment 2: dwell settings', '02_dwell_settings')
    figure(sessions[2], 'lighting', ['Normal Lighting', 'Dim Lighting'], ['Normal lighting', 'Dim lighting'], 'Experiment 3: lighting conditions (K=6)', '03_lighting')
    overall = table(groups[1:4])
    basic = table(groups[4:10])
    dwell = table(groups[10:13])
    light = table(groups[13:15])
    text = f'''# HW5 實驗結果與分析

## 資料與檢查

2026 年 11 月 6 日收集的三份正式 CSV 共 75 次，實驗一 30 次、實驗二 27 次、實驗三 18 次。各指令、條件與重複次數完整，沒有重複 trial；20 次 Pilot 觸發獨立保存，不納入正式統計。原始 CSV 未改動。逐項驗證與來源 SHA256 見 [validation.json](validation.json)。

三份來源為：

{chr(10).join('- [' + p.name + '](../' + p.name + ')' for p in paths)}

三個 confidence 均為 0.5、cooldown 為 1 秒、timeout 為 8 秒，MediaPipe 版本 0.10.35，模型雜湊一致且與本機模型相符。實驗一、三的 K=6；實驗二為 3／6／10。各試驗記錄的平均處理 FPS 為 14.90–15.50。實驗三先執行正常光線，再執行昏暗光線。

## 整體結果

{overall}

75/75 次正確，整體成功率 100%。三組的誤觸、逾時、全程未偵測次數均為 0。這是本次受控操作的指令成功率，不能解讀為每個影格都正確偵測到手，亦不代表所有使用者與環境都會達到 100%。各組任務與條件不同，合併平均延遲不適合用來比較辨識方法。

觸發時間從按下「開始計時」到第一個指令被辨識，包含使用者伸手、移動、區域對準與連續影格確認，不是單純的模型推論時間。下表與圖表保留所有試驗，沒有刪除較慢樣本；標準差採樣本標準差，圖中每點代表一次試驗，實線為平均、虛線為中位數。

## 實驗一：六個指令

{basic}

![六指令觸發時間](01_basic_accuracy.png)

六項指令各成功 5/5 次。Z1 Previous 平均 1.59 秒最快，Z4 Zoom Out 平均 3.06 秒最慢；Z3、Z4、Z5 約為 2.84–3.06 秒。底部工具列可能需要較多手腕定位時間，但資料沒有分開記錄移動與確認階段，因此不能直接歸因於區域尺寸或辨識演算法。

最慢的 E1-006（Z5）為 5064.8 ms，76 個影格中有 70 個無手偵測，且沒有有手轉無手的事件。這與較晚出現可偵測手部相容，無法單靠 CSV 判定是使用者等待、手未進入畫面，或手已在畫面但未被偵測。

## 實驗二：停留確認長度

{dwell}

![三組停留設定](02_dwell_settings.png)

Short、Medium、Long 均成功 9/9 次。平均觸發時間由 1471.5 ms 增至 2023.0 ms、2902.4 ms；Long 比 Short 多 1430.9 ms（約 97.2%）。中位數也依序增加：1368.1、1800.2、2260.4 ms。三組各包含相同的三個指令與重複次數，組成平衡。

約 15 FPS 時，K=3／6／10 的 K/FPS 時間尺度約為 0.20／0.40／0.67 秒；這只用來理解影格設定，不能當成實測停留時間。觀察到的總延遲差距較大，表示使用者進入操作區的時機與辨識過程也影響結果。

Long 有兩次約 6.19 秒的試驗，均保留於分析：E2-001 有 93 個影格，其中 83 個無手偵測；E2-020 有 93 個影格，其中 73 個無手偵測，並有 2 次有手轉無手事件。Long 的標準差因此達 1951.4 ms，平均值比中位數更受長尾影響。

本次資料支持「較短 K 的總操作時間較短」的描述，但三組皆無誤觸，沒有觀察到長 K 降低誤觸的效益。因此尚無法用本次結果證明 Long 更穩定，或認定 Short 在快速掃過區域時仍同樣可靠。正式設定保留 Medium K=6 是現有 baseline；若要選出最佳設定，需要補測快速經過區域與邊界干擾等情境。

## 實驗三：正常與昏暗光線

{light}

![光線條件比較](03_lighting.png)

正常與昏暗光線皆成功 9/9 次。昏暗平均多 56.8 ms（約 3.9%），中位數僅多 4.9 ms；昏暗條件的標準差較大（684.1 vs 332.2 ms）。樣本範圍重疊，本次沒有觀察到指令成功率下降，也沒有足夠證據認定兩種光線等效或存在穩定的速度差異。

兩條件各有三個相同指令、各重複 3 次，但本次實際順序為正常後昏暗，仍可能受到熟練或疲勞影響。CSV 未記錄照度、相機曝光與操作距離，不能將結果外推到所有低光環境。

## 偵測事件與失敗指標

三組累計 2428 個處理影格，其中 1814 個無手偵測，另有 11 次有手轉無手事件與 1 個雙手影格。這些事件沒有讓正式試驗誤觸或逾時。由於計時從手移出畫面時開始，`no_hand_frames` 包含伸手前的空窗，不能將 1814/2428 當作偵測失敗率。

`detection_failure` 的定義是「試驗逾時且全程未偵測到手」，本次為 0；11 次 `tracking_loss_count` 也可能包含主動移手，不能全部歸類為演算法故障。缺少逐影格真實標記與事件時間序列，無法算出真正的影格偵測準確率、失去追蹤時長或每次重新累積的停留時間。

## 限制與可寫入報告的結論

這批資料顯示，在本次環境與操作流程中，手腕定位搭配 K 影格確認可以完成六項指令，75 次均成功。K 越長的組別總觸發時間越長；在本次正常與昏暗兩個條件下，均未出現指令失敗。由於所有條件的成功率都達上限，準確率無法進一步區分設定優劣。

CSV 未提供參與者識別碼與人數，且每個細分條件只有 3 或 5 次；不能把 75 次當成 75 位獨立使用者。本分析採描述統計，不宣稱統計顯著性，也不對平均值差距做因果推論。若需進一步研究，可增加不同使用者、量測光照，並加入快速掠過、邊界停留、遮擋與背景移動的試驗。

HW5 以手腕位置選取區域，HW4 以前景變化比例選取區域，兩者的輸入依據不同。這批資料沒有同步的 HW4 對照條件，因此可比較辨識原理，不能據此宣稱 HW5 的實驗準確率優於 HW4。

## 重現

在作業五資料夾執行 `python analyze_experiments.py`。程式會驗證三份指定來源，重建本分析、PNG／SVG 圖表、[摘要指標 CSV](summary_metrics.csv) 與 [基本統計表](basic_summary.md)。需要 `requirements.txt` 與 matplotlib（已列於 requirements-lock.txt）。
'''
    (OUT / 'RESULTS_ANALYSIS.md').write_text(text, encoding='utf-8')
    print(json.dumps({'validation': validation['status'], 'trials': len(all_rows), 'correct': stats(all_rows)['correct'], 'output': str(OUT)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
