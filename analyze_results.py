"""Summarize actual HW5 CSV rows; never fill missing trials or timeout latency."""

import argparse
import csv
from pathlib import Path
from statistics import mean


def truth(value):
    return str(value).lower() == 'true'


def summarize(rows):
    successes = [r for r in rows if truth(r['correct'])]
    latencies = [float(r['trigger_time_ms']) for r in successes if r.get('trigger_time_ms')]
    return [len(rows), '{:.1f}%'.format(100 * len(successes) / len(rows)) if rows else '—',
            sum(truth(r['false_trigger']) for r in rows),
            sum(truth(r['missed_trigger']) for r in rows),
            sum(truth(r['detection_failure']) for r in rows),
            '{:.1f}'.format(mean(latencies)) if latencies else '—']


def build_report(paths):
    rows = []
    seen = set()
    for path in paths:
        with Path(path).open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                if row.get('experiment') == 'pilot':
                    continue
                required = {'session_id', 'trial_id', 'experiment', 'correct', 'false_trigger', 'missed_trigger', 'detection_failure'}
                if not required.issubset(row):
                    raise ValueError('{} 不是 HW5 正式實驗 CSV'.format(path))
                identity = (row['session_id'], row['trial_id'])
                if identity in seen:
                    raise ValueError('重複試驗：{}；請勿將同一份資料重複納入'.format(identity))
                seen.add(identity)
                rows.append(row)
    if not rows:
        raise ValueError('沒有可分析的正式試驗資料')
    lines = ['# HW5 實驗資料摘要', '', '僅統計 CSV 中實際完成的試驗。成功率包含誤觸與逾時試驗；平均觸發時間只計正確觸發，逾時不填入 0。', '',
             '「全程未偵測」指逾時且有效影格中從未偵測到手，不能單憑這個欄位判定使用者當時確實有伸手；請搭配備註與證據圖。', '',
             '| 分組 | 次數 | 成功率 | 誤觸 | 逾時 | 全程未偵測 | 正確觸發平均 ms |',
             '|---|---:|---:|---:|---:|---:|---:|']
    groups = {'全部': rows}
    for row in rows:
        labels = ['{} / {}'.format(row['session_id'], row['experiment']),
                  '{} / {}'.format(row['experiment'], row['target_command'])]
        if row['experiment'] == 'experiment2':
            labels.append('實驗二 / {} / K={}'.format(row['dwell_level'], row['dwell_frames']))
        if row['experiment'] == 'experiment3':
            labels.append('實驗三 / ' + row['lighting'])
        for label in labels:
            groups.setdefault(label, []).append(row)
    for label, group in groups.items():
        lines.append('| {} | {} |'.format(label, ' | '.join(map(str, summarize(group)))))
    lines += ['', '正式排程每個完整 session 應為：實驗一 30、實驗二 27、實驗三 18 次。中途停止的 session 應重做或在報告中明確說明，不會自動補齊。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='分析 HW5 實際試驗 CSV')
    parser.add_argument('csv_files', nargs='*', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    paths = args.csv_files or sorted((Path(__file__).parent / 'results').glob('experiment*.csv'))
    try:
        report = build_report(paths)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding='utf-8')
        print(args.output)
    else:
        print(report)


if __name__ == '__main__':
    main()
