#!/usr/bin/env python3
"""
AI名师课堂分析服务
流程：B站链接解析 → 音频下载 → Whisper识别 → OpenCC简体转换 → 深度教学分析
"""
import os
import re
import json
import time
import uuid
import asyncio
import subprocess
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import whisper
from opencc import OpenCC

app = FastAPI(title="AI名师课堂分析服务")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局任务存储
tasks: Dict[str, Dict[str, Any]] = {}
cc = OpenCC('t2s')
model = None

def get_model():
    global model
    if model is None:
        print("加载Whisper模型...")
        model = whisper.load_model("tiny")
        print("Whisper模型加载完成")
    return model

class AnalyzeRequest(BaseModel):
    url: str
    language: str = "zh"

def extract_bvid(url: str) -> Optional[str]:
    """从B站链接提取BV号"""
    patterns = [
        r'BV[a-zA-Z0-9]+',
        r'bvid=([a-zA-Z0-9]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1) if 'bvid' in pattern else match.group(0)
    return None

def get_video_info(bvid: str) -> Dict[str, Any]:
    """获取B站视频信息"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.bilibili.com'
    }
    # 获取视频信息
    resp = requests.get(f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}', headers=headers, timeout=10)
    data = resp.json()
    if data.get('code') != 0:
        raise Exception(f"获取视频信息失败: {data.get('message')}")
    info = data['data']
    # 获取分P信息（取第一P或指定P）
    cid = info['cid']
    pages = info.get('pages', [])
    if pages:
        cid = pages[0]['cid']
    return {
        'bvid': bvid,
        'cid': cid,
        'title': info['title'],
        'owner': info['owner']['name'],
        'duration': info['duration'],
        'desc': info.get('desc', ''),
        'pic': info.get('pic', '')
    }

def get_audio_url(bvid: str, cid: int) -> str:
    """获取音频流地址"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'https://www.bilibili.com/video/{bvid}'
    }
    resp = requests.get(
        f'https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=64&fnval=16',
        headers=headers, timeout=10
    )
    data = resp.json()
    if data.get('code') != 0:
        raise Exception(f"获取音频地址失败: {data.get('message')}")
    dash = data['data'].get('dash', {})
    audio_list = dash.get('audio', [])
    if not audio_list:
        raise Exception("未找到音频流")
    return audio_list[0]['baseUrl']

def download_audio(audio_url: str, output_path: str, bvid: str):
    """下载音频"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'https://www.bilibili.com/video/{bvid}'
    }
    resp = requests.get(audio_url, headers=headers, stream=True, timeout=60)
    with open(output_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    # 转换为mp3
    mp3_path = output_path.replace('.m4s', '.mp3')
    subprocess.run(['ffmpeg', '-y', '-i', output_path, '-acodec', 'libmp3lame', '-q:a', '4', mp3_path],
                   capture_output=True, timeout=120)
    return mp3_path

def transcribe_audio(audio_path: str, task_id: str):
    """用Whisper识别音频"""
    model = get_model()
    result = model.transcribe(audio_path, language='zh', fp16=False, verbose=False)
    segments = []
    for seg in result['segments']:
        text = seg['text'].strip()
        if text:
            # OpenCC转简体
            text = cc.convert(text)
            time_str = f"{int(seg['start']//60):02d}:{int(seg['start']%60):02d}"
            # 识别语气
            tone = 'calm'
            if any(q in text for q in ['吗', '呢', '吧', '？', '?', '怎么', '什么', '为什么', '如何', '是不是', '对不对', '有没有']):
                tone = 'question'
            elif any(k in text for k in ['重点', '关键', '记住', '注意', '必须', '核心', '重要']):
                tone = 'passion'
            elif any(e in text for e in ['对', '很好', '不错', '棒', '厉害']):
                tone = 'encourage'
            segments.append({
                'time': time_str,
                'text': text,
                'tone': tone,
                'start': round(seg['start'], 1),
                'end': round(seg['end'], 1)
            })
            # 更新进度
            if task_id in tasks:
                progress = min(90, int(seg['start'] / result['segments'][-1]['end'] * 70) + 20)
                tasks[task_id]['progress'] = progress
    return segments

def deep_analysis(segments: list, video_info: dict) -> Dict[str, Any]:
    """深度教学分析"""
    full_text = ' '.join([s['text'] for s in segments])

    # 识别教学环节
    teaching_segments = []
    current_seg = {'title': '课程导入', 'start_time': '', 'sentences': [], 'type': 'intro'}

    def detect_segment(text, time_str):
        min_val = int((time_str or '00:00').split(':')[0]) or 0
        if any(k in text for k in ['同学们好', '今天我们来讲', '今天我们学习', '哈喽', '大家好', '上课']):
            return {'title': '课程导入', 'type': 'intro'}
        if any(k in text for k in ['第一题', '第二题', '第三题', '如图', '下图', '图甲', '图乙', '例题']):
            return {'title': '例题精讲', 'type': 'example'}
        if any(k in text for k in ['我们来做', '做一下题', '练习', '随堂', '检测', '巩固']):
            return {'title': '课堂练习', 'type': 'practice'}
        if any(k in text for k in ['总结', '今天我们学习了', '归纳', '梳理', '讲到这里', '下课']):
            return {'title': '课堂总结', 'type': 'summary'}
        if any(k in text for k in ['实验', '验证', '设计', '探究', '脊蛙', '反射弧']) and min_val > 5:
            return {'title': '实验探究', 'type': 'experiment'}
        if any(k in text for k in ['原理', '核心', '关键', '重点', '方法', '分析', '概念', '定义']) and min_val < 15:
            return {'title': '新知讲解', 'type': 'lecture'}
        return None

    for s in segments:
        seg = detect_segment(s['text'], s['time'])
        if seg and current_seg['title'] != seg['title'] and current_seg['sentences']:
            teaching_segments.append(current_seg)
            current_seg = {'title': seg['title'], 'start_time': s['time'], 'sentences': [], 'type': seg['type']}
        if not current_seg['start_time']:
            current_seg['start_time'] = s['time']
        current_seg['sentences'].append(s)
    if current_seg['sentences']:
        teaching_segments.append(current_seg)

    # 提取知识点
    knowledge_points = []
    bio_keywords = ['细胞', '神经', '激素', '调节', '反射', '突触', '电位', '基因', '遗传', '生态',
                    '进化', '代谢', '光合', '呼吸', '免疫', '稳态', '器官', '组织', '系统',
                    'DNA', 'RNA', '蛋白质', '酶', 'ATP', '染色体', '减数分裂', '有丝分裂']
    for kw in bio_keywords:
        if kw in full_text and kw not in knowledge_points:
            knowledge_points.append(kw)

    # 教学技巧分析
    techniques = []
    question_count = sum(1 for s in segments if s['tone'] == 'question')
    if question_count > 5:
        techniques.append(f'互动提问丰富（{question_count}次提问），善于启发学生思考')
    if any('实验' in s['text'] for s in segments):
        techniques.append('结合实验讲解，理论联系实际')
    if any('例题' in s['text'] or '题' in s['text'] for s in segments):
        techniques.append('例题精讲，注重解题思路培养')
    if any('总结' in s['text'] or '归纳' in s['text'] for s in segments):
        techniques.append('课堂总结到位，知识体系完整')

    # 生成思维导图数据
    mindmap = {
        'title': video_info['title'],
        'children': [
            {'name': seg['title'], 'children': [{'name': s['text'][:20]} for s in seg['sentences'][:3]]}
            for seg in teaching_segments[:6]
        ]
    }

    return {
        'teaching_segments': teaching_segments,
        'knowledge_points': knowledge_points[:10],
        'techniques': techniques,
        'mindmap': mindmap,
        'question_count': question_count,
        'total_duration': video_info['duration'],
        'word_count': len(full_text)
    }

async def process_task(task_id: str, url: str):
    """后台处理任务"""
    try:
        tasks[task_id]['status'] = 'processing'
        tasks[task_id]['progress'] = 5
        tasks[task_id]['message'] = '解析视频链接...'

        # 1. 提取BV号
        bvid = extract_bvid(url)
        if not bvid:
            raise Exception('无法识别B站视频链接')
        tasks[task_id]['progress'] = 10
        tasks[task_id]['message'] = '获取视频信息...'

        # 2. 获取视频信息
        video_info = get_video_info(bvid)
        tasks[task_id]['video_info'] = video_info
        tasks[task_id]['progress'] = 15
        tasks[task_id]['message'] = f'获取到视频：{video_info["title"]}'

        # 3. 获取音频地址
        tasks[task_id]['message'] = '获取音频流地址...'
        audio_url = get_audio_url(bvid, video_info['cid'])
        tasks[task_id]['progress'] = 20

        # 4. 下载音频
        tasks[task_id]['message'] = '下载音频中...'
        audio_dir = os.path.join(os.path.dirname(__file__), 'audio')
        os.makedirs(audio_dir, exist_ok=True)
        raw_path = os.path.join(audio_dir, f'{task_id}.m4s')
        mp3_path = download_audio(audio_url, raw_path, bvid)
        tasks[task_id]['progress'] = 25
        tasks[task_id]['message'] = '音频下载完成，开始识别...'

        # 5. Whisper识别
        segments = transcribe_audio(mp3_path, task_id)
        tasks[task_id]['progress'] = 90
        tasks[task_id]['message'] = f'识别完成，共{len(segments)}段，正在深度分析...'

        # 6. 深度分析
        analysis = deep_analysis(segments, video_info)
        tasks[task_id]['progress'] = 95
        tasks[task_id]['message'] = '生成教学分析报告...'

        # 7. 整理结果
        result = {
            'id': task_id,
            'video_info': video_info,
            'transcript': segments,
            'analysis': analysis,
            'created_at': time.time()
        }
        tasks[task_id]['result'] = result
        tasks[task_id]['progress'] = 100
        tasks[task_id]['status'] = 'completed'
        tasks[task_id]['message'] = '分析完成！'

        # 清理临时文件
        try:
            os.remove(raw_path)
            os.remove(mp3_path)
        except:
            pass

    except Exception as e:
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['message'] = f'分析失败：{str(e)}'
        tasks[task_id]['error'] = str(e)

@app.post("/api/analyze")
async def analyze_video(req: AnalyzeRequest):
    """提交分析任务"""
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        'id': task_id,
        'status': 'pending',
        'progress': 0,
        'message': '等待处理...',
        'created_at': time.time()
    }
    # 启动后台任务
    asyncio.create_task(process_task(task_id, req.url))
    return {'task_id': task_id, 'status': 'pending'}

@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """查询任务状态"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    task = tasks[task_id]
    return {
        'task_id': task_id,
        'status': task['status'],
        'progress': task['progress'],
        'message': task.get('message', ''),
        'video_info': task.get('video_info')
    }

@app.get("/api/result/{task_id}")
async def get_result(task_id: str):
    """获取分析结果"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    task = tasks[task_id]
    if task['status'] != 'completed':
        raise HTTPException(status_code=400, detail="任务尚未完成")
    return task['result']

@app.get("/api/health")
async def health():
    return {'status': 'ok', 'model_loaded': model is not None}

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', 8890))
    uvicorn.run(app, host='0.0.0.0', port=port)
