// 逐字稿AI修正脚本（node版本）
const https = require('https');
const fs = require('fs');

const API_URL = 'ark.cn-beijing.volces.com';
const API_KEY = Buffer.from('YXJrLTk2YTk1MjU0LTE2YTktNDRmZC04YTg2LTgzNDQwM2U1ZmY1ZS05Yzg2Zg==','base64').toString();
const ENDPOINT = Buffer.from('ZXAtMjAyNjA5MTMxNjI4NDAtYmZybnQ=','base64').toString();

function callDoubao(prompt, maxTokens = 3000) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify({
      model: ENDPOINT,
      messages: [{role: 'user', content: prompt}],
      max_tokens: maxTokens,
      temperature: 0.3
    });
    const options = {
      hostname: API_URL,
      path: '/api/v3/chat/completions',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${API_KEY}`,
        'Content-Length': Buffer.byteLength(data)
      }
    };
    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => body += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(body);
          if (json.choices && json.choices[0]) {
            resolve(json.choices[0].message.content);
          } else {
            reject(new Error(JSON.stringify(json).substring(0, 200)));
          }
        } catch (e) {
          reject(e);
        }
      });
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

async function correctBatch(segments, courseTitle, batchIdx, totalBatches) {
  let inputText = '';
  segments.forEach(s => {
    inputText += `[${s.time}] ${s.text}\n`;
  });

  const prompt = `你是高中生物教学专家。请修正以下课堂逐字稿的识别错误。

课程：${courseTitle}
批次：${batchIdx + 1}/${totalBatches}

修正要求：
1. 修正高中生物专业术语错误（如"模电位"→"膜电位"，"那例子"→"钠离子"，"甲例子"→"钾离子"，"突处"→"突触"，"神经先微"→"神经纤维"等）
2. 通顺语句，使上下文连贯，去除明显的识别错误
3. 保持原意，不要删减教学内容
4. 保留时间戳格式 [MM:SS]
5. 不要添加解释，只输出修正后的逐字稿
6. 全部使用简体中文
7. 不要改变句子数量，每句一行

原始逐字稿：
${inputText}

请输出修正后的逐字稿（每行一条，格式：[时间] 修正后文本）：`;

  for (let retry = 0; retry < 3; retry++) {
    try {
      const result = await callDoubao(prompt, 4000);
      // 解析结果
      const corrected = [];
      const lines = result.trim().split('\n');
      lines.forEach(line => {
        line = line.trim();
        if (!line) return;
        const match = line.match(/\[(\d+:\d+)\]\s*(.*)/);
        if (match) {
          corrected.push({time: match[1], text: match[2].trim()});
        }
      });
      if (corrected.length > 0) return corrected;
      console.log(`    解析失败，重试${retry + 1}...`);
    } catch (e) {
      console.log(`    调用失败: ${e.message.substring(0, 50)}，重试${retry + 1}...`);
    }
    await new Promise(r => setTimeout(r, 2000));
  }
  return null;
}

async function processTranscript(inputFile, outputFile, courseTitle, batchSize = 10) {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`处理: ${courseTitle}`);
  console.log(`输入: ${inputFile}`);
  console.log(`${'='.repeat(60)}`);

  const segments = JSON.parse(fs.readFileSync(inputFile, 'utf-8'));
  console.log(`原始段数: ${segments.length}`);

  const totalBatches = Math.ceil(segments.length / batchSize);
  const allCorrected = [];

  for (let i = 0; i < totalBatches; i++) {
    const start = i * batchSize;
    const end = Math.min(start + batchSize, segments.length);
    const batch = segments.slice(start, end);

    process.stdout.write(`  批次 ${i + 1}/${totalBatches}: 段 ${start + 1}-${end}... `);

    const corrected = await correctBatch(batch, courseTitle, i, totalBatches);

    if (corrected) {
      // 保留原始语气标记
      corrected.forEach((s, j) => {
        const origIdx = start + j;
        s.tone = segments[origIdx] ? segments[origIdx].tone || 'calm' : 'calm';
      });
      allCorrected.push(...corrected);
      console.log(`✅ 修正${corrected.length}段`);
    } else {
      console.log(`❌ 失败，保留原始`);
      batch.forEach(s => {
        allCorrected.push({time: s.time, text: s.text, tone: s.tone || 'calm'});
      });
    }

    // 保存中间结果
    fs.writeFileSync(outputFile, JSON.stringify(allCorrected, null, 2), 'utf-8');

    await new Promise(r => setTimeout(r, 500));
  }

  const totalChars = allCorrected.reduce((sum, s) => sum + s.text.length, 0);
  console.log(`\n✅ 完成！修正后段数: ${allCorrected.length}`);
  console.log(`总字数: ${totalChars}`);
  console.log(`输出: ${outputFile}`);

  return allCorrected;
}

// 主程序
async function main() {
  const idx = process.argv[2] ? parseInt(process.argv[2]) : 2; // 默认处理第3个

  const transcripts = [
    {input: 'audio/electric_meter.json', output: 'audio/electric_meter_corrected.json', title: '电表偏转问题及实验设计 - 高中生物神经调节'},
    {input: 'audio/nervous_system.json', output: 'audio/nervous_system_corrected.json', title: '神经系统的分级调节 - 高中生物'},
    {input: 'audio/brain_function_transcript.json', output: 'audio/brain_function_corrected.json', title: '人脑的高级功能 - 高中生物'},
  ];

  const t = transcripts[idx];
  if (!t) {
    console.log('无效的索引');
    return;
  }

  await processTranscript(t.input, t.output, t.title, 10);
}

main().catch(console.error);
