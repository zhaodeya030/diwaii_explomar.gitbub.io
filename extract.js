export const config = {
  maxDuration: 60,
};

const EXTRACTION_PROMPT = `你是一个数据提取助手。用户会给你一个船厂(boat manufacturer)的官方网站 URL。请访问这个网站,抓取公司信息,按下面的 JSON 格式严格回复(不要 markdown 代码块,直接 JSON 对象):

{
  "company_name": "公司全名",
  "country": "Country in English (如 Italy, France, United States)",
  "category": "二选一: 'Boat Manufacturer' (实际造船的厂家) 或 'Boat (Yacht) Designer' (只做设计/工程不造船)",
  "business_description": "1-2 句话描述他们做什么",
  "website": "原 URL",
  "email": "primary contact 邮箱(找首页/About/Contact 页)",
  "phone": "电话或 whatsapp",
  "linkedin": "LinkedIn URL(找官网或 Footer 链接)",
  "facebook": "Facebook 或 Instagram URL(其中之一,优先 Facebook)"
}

country 字段务必尽力推断,顺序如下:
1. 网页里明确写的地址 / 国家名(优先)
2. 电话国际区号 (+39 = Italy, +965 = Kuwait, +1 = USA/Canada, +44 = UK 等)
3. 域名后缀 (.it=Italy, .kw=Kuwait, .br=Brazil, .de=Germany, .fr=France, .au=Australia, .nz=New Zealand, .nl=Netherlands, .es=Spain, .gr=Greece, .pt=Portugal, .ru=Russia, .pl=Poland, .se=Sweden, .no=Norway, .dk=Denmark, .fi=Finland, .ie=Ireland, .uk=UK, .ca=Canada, .mx=Mexico, .cl=Chile, .ar=Argentina, .co=Colombia, .pe=Peru, .za=South Africa, .ae=UAE, .sa=Saudi Arabia, .tr=Turkey, .il=Israel, .jp=Japan, .kr=Korea, .cn=China, .hk=Hong Kong, .tw=Taiwan, .sg=Singapore, .my=Malaysia, .th=Thailand, .id=Indonesia, .ph=Philippines, .vn=Vietnam, .in=India 等)
4. 城市名(找到城市后查它在哪国,如 Dubai → United Arab Emirates, Mumbai → India)
只有这四种线索都找不到才填空字符串。

其它字段找不到都可以填空字符串。不要瞎猜邮箱。

URL: `;

const GEMINI_CONFIGS = [
  { model: 'gemini-2.5-flash', tool: 'url_context' },
  { model: 'gemini-2.5-flash-lite', tool: 'url_context' },
  { model: 'gemini-flash-latest', tool: 'url_context' },
  { model: 'gemini-2.0-flash-lite', tool: 'url_context' },
  { model: 'gemini-2.0-flash', tool: 'url_context' },
  { model: 'gemini-2.5-flash', tool: 'google_search' },
  { model: 'gemini-2.5-flash-lite', tool: 'google_search' },
];

function parseExtractedJson(text) {
  let jsonStr = String(text || '').trim();
  const match = jsonStr.match(/\{[\s\S]*\}/);
  if (match) jsonStr = match[0];
  return JSON.parse(jsonStr);
}

function normalizeResult(info, originalUrl) {
  const cat = String(info.category || '').toLowerCase().includes('design')
    ? 'Boat (Yacht) Designer'
    : 'Boat Manufacturer';

  return {
    company_name: info.company_name || '',
    country: info.country || '',
    category: cat,
    business_description: info.business_description || '',
    website: info.website || originalUrl,
    email: info.email || '',
    phone: info.phone || '',
    linkedin: info.linkedin || '',
    facebook: info.facebook || '',
  };
}

async function callGeminiOnce(apiKey, model, tool, url) {
  const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
  const body = {
    contents: [{
      role: 'user',
      parts: [{ text: EXTRACTION_PROMPT + url }],
    }],
    generationConfig: { temperature: 0.1 },
  };

  if (tool === 'url_context') body.tools = [{ url_context: {} }];
  if (tool === 'google_search') body.tools = [{ google_search: {} }];

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  const raw = await response.text();
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error(`Gemini 返回不是 JSON: ${raw.slice(0, 200)}`);
  }

  if (!response.ok) {
    const message = data?.error?.message || raw.slice(0, 200);
    throw new Error(`Gemini ${model} HTTP ${response.status}: ${message}`);
  }

  const finishReason = data?.candidates?.[0]?.finishReason;
  const text = data?.candidates?.[0]?.content?.parts?.map(part => part.text || '').join('') || '';
  if (!text) {
    throw new Error(`Gemini ${model} 返回空响应${finishReason ? ` (${finishReason})` : ''}`);
  }

  return text;
}

async function callGemini(url) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) throw new Error('Vercel 环境变量 GEMINI_API_KEY 未配置');

  let lastError;
  for (const cfg of GEMINI_CONFIGS) {
    try {
      const text = await callGeminiOnce(apiKey, cfg.model, cfg.tool, url);
      return parseExtractedJson(text);
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error('Gemini 调用失败');
}

async function callOpenAI(url) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error('Vercel 环境变量 OPENAI_API_KEY 未配置');

  const response = await fetch('https://api.openai.com/v1/responses', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: 'gpt-4o-mini',
      tools: [{ type: 'web_search_preview' }],
      input: EXTRACTION_PROMPT + url,
    }),
  });

  const raw = await response.text();
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error(`OpenAI 返回不是 JSON: ${raw.slice(0, 200)}`);
  }

  if (!response.ok) {
    const message = data?.error?.message || raw.slice(0, 200);
    throw new Error(`OpenAI HTTP ${response.status}: ${message}`);
  }

  const messageOut = (data.output || []).find(item => item.type === 'message');
  const text = messageOut?.content?.find(item => item.type === 'output_text')?.text || data.output_text || '';
  if (!text) throw new Error('OpenAI 返回空响应');

  return parseExtractedJson(text);
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Only POST requests are allowed' });
  }

  const { url } = req.body || {};
  if (!url || typeof url !== 'string') {
    return res.status(400).json({ error: '缺少 url' });
  }

  try {
    new URL(url);
  } catch {
    return res.status(400).json({ error: 'URL 格式不正确，请输入完整网址，例如 https://example.com' });
  }

  let lastError;

  if (process.env.GEMINI_API_KEY) {
    try {
      const info = await callGemini(url);
      return res.status(200).json(normalizeResult(info, url));
    } catch (error) {
      lastError = error;
    }
  }

  if (process.env.OPENAI_API_KEY) {
    try {
      const info = await callOpenAI(url);
      return res.status(200).json(normalizeResult(info, url));
    } catch (error) {
      lastError = error;
    }
  }

  return res.status(500).json({
    error: lastError?.message || '没有配置 GEMINI_API_KEY 或 OPENAI_API_KEY',
  });
}
