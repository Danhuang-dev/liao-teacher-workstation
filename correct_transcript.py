#!/usr/bin/env python3
"""
逐字稿AI智能修正脚本
调用豆包API对Whisper识别结果进行：
1. 高中生物专业术语修正
2. 语句通顺化、上下文连贯
3. 去除口语废话（保留教学语气标记）
4. 保持原意和时间戳
"""
import json, time, requests, sys
from opencc import OpenCC

cc = OpenCC('t2s')

# 豆包API配置
API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
import base64
API_KEY = base64.b64decode('YXJrLTk2YTk1MjU0LTE2YTktNDRmZC04YTg2LTgzNDQwM2U1ZmY1ZS05Yzg2Zg==').decode()
ENDPOINT = base64.b64decode('ZXAtMjAyNjA5MTMxNjI4NDAtYmZybnQ=').decode()

def call_doubao(prompt, max_tokens=2000):
    """调用豆包API"""
    try:
        resp = requests.post(
            API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}"
            },
            json={
                "model": ENDPOINT,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": max_tokens
            },
            timeout=60
        )
        data = resp.json()
        if data.get("choices"):
            return data["choices"][0]["message"]["content"]
        print(f"API错误: {data}")
        return None
    except Exception as e:
        print(f"调用失败: {e}")
        return None

def correct_batch(segments, course_title, batch_idx, total_batches):
    """修正一批逐字稿"""
    # 构建输入文本
    input_text = ""
    for s in segments:
        input_text += f"[{s['time']}] {s['text']}\n"
    
    prompt = f"""你是高中生物教学专家。请修正以下课堂逐字稿的识别错误。

课程：{course_title}
批次：{batch_idx+1}/{total_batches}

修正要求：
1. 修正高中生物专业术语错误（如"模电位"→"膜电位"，"那例子"→"钠离子"，"甲例子"→"钾离子"，"突处"→"突触"等）
2. 通顺语句，使上下文连贯，去除明显的识别错误
3. 保持原意，不要删减教学内容
4. 保留时间戳格式 [MM:SS]
5. 不要添加解释，只输出修正后的逐字稿
6. 全部使用简体中文

原始逐字稿：
{input_text}

请输出修正后的逐字稿（每行一条，格式：[时间] 修正后文本）："""
    
    result = call_doubao(prompt, max_tokens=3000)
    if not result:
        return None
    
    # 解析结果
    corrected = []
    lines = result.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 提取时间戳和文本
        import re
        match = re.match(r'\[(\d+:\d+)\]\s*(.*)', line)
        if match:
            time_str = match.group(1)
            text = match.group(2).strip()
            # 简繁转换
            text = cc.convert(text)
            corrected.append({"time": time_str, "text": text})
    
    return corrected

def process_transcript(input_file, output_file, course_title, batch_size=12):
    """处理整个逐字稿"""
    print(f"\n{'='*60}")
    print(f"处理: {course_title}")
    print(f"输入: {input_file}")
    print(f"{'='*60}")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        segments = json.load(f)
    
    print(f"原始段数: {len(segments)}")
    
    # 分批处理
    total_batches = (len(segments) + batch_size - 1) // batch_size
    all_corrected = []
    
    for i in range(total_batches):
        start = i * batch_size
        end = min(start + batch_size, len(segments))
        batch = segments[start:end]
        
        print(f"  批次 {i+1}/{total_batches}: 段 {start+1}-{end}...", end=" ", flush=True)
        
        # 重试机制
        corrected = None
        for retry in range(3):
            corrected = correct_batch(batch, course_title, i, total_batches)
            if corrected and len(corrected) > 0:
                break
            print(f"重试{retry+1}...", end=" ", flush=True)
            time.sleep(2)
        
        if corrected:
            # 保留原始语气标记
            for j, s in enumerate(corrected):
                orig_idx = start + j
                if orig_idx < len(segments):
                    s['tone'] = segments[orig_idx].get('tone', 'calm')
                else:
                    s['tone'] = 'calm'
            all_corrected.extend(corrected)
            print(f"✅ 修正{len(corrected)}段")
        else:
            # 修正失败，保留原始
            print(f"❌ 失败，保留原始")
            for s in batch:
                all_corrected.append({
                    "time": s["time"],
                    "text": cc.convert(s["text"]),
                    "tone": s.get("tone", "calm")
                })
        
        time.sleep(1)  # 避免API限流
    
    # 保存
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_corrected, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 完成！修正后段数: {len(all_corrected)}")
    print(f"输出: {output_file}")
    
    # 统计
    total_chars = sum(len(s['text']) for s in all_corrected)
    print(f"总字数: {total_chars}")
    
    return all_corrected

if __name__ == '__main__':
    # 处理3个逐字稿
    transcripts = [
        ("audio/electric_meter.json", "audio/electric_meter_corrected.json", "电表偏转问题及实验设计 - 高中生物神经调节"),
        ("audio/nervous_system.json", "audio/nervous_system_corrected.json", "神经系统的分级调节 - 高中生物"),
        ("audio/brain_function_transcript.json", "audio/brain_function_corrected.json", "人脑的高级功能 - 高中生物"),
    ]
    
    # 只处理指定的文件（如果有参数）
    if len(sys.argv) > 1:
        idx = int(sys.argv[1])
        transcripts = [transcripts[idx]]
    
    for input_f, output_f, title in transcripts:
        try:
            process_transcript(input_f, output_f, title, batch_size=10)
        except Exception as e:
            print(f"处理失败: {e}")
            import traceback
            traceback.print_exc()
