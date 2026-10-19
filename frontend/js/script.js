'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const tools = [
  { id: 'prices', title: 'Price, in perspective.', short: 'Price comparator', description: 'Compare permitted product pages and export structured prices.', icon: 'chart', keywords: 'web scraping data beautifulsoup prices compare shopping' },
  { id: 'voice', title: 'A voice for your ideas.', short: 'Voice assistant', description: 'Think out loud with a conversational AI assistant.', icon: 'mic', keywords: 'ai groq speech microphone conversation voice chat' },
  { id: 'hands', title: 'Motion, understood.', short: 'Hand detection', description: 'Discover 21 hand landmarks from an image or camera.', icon: 'hand', keywords: 'vision camera video photo opencv mediapipe hands' },
  { id: 'documents', title: 'Knowledge, unlocked.', short: 'Document Q&A', description: 'Your documents. Your questions. Answers grounded in what matters.', icon: 'file', keywords: 'rag pdf txt documents knowledge embeddings faiss ai' }
];
const workspace = $('#workspace');
const content = $('#workspaceContent');
let cleanup = () => {};
let lifecycle = 0;
let activeFilter = 'all';
let feature = 3;
let toastTimer;
let status = null;
const priceItems = [];
let priceResults = [];
const conversation = [];
let documentSession = null;

function icon(name) { return `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`; }
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 4200);
}
function notice(target, message, error = false) {
  target.replaceChildren(node('p', message, `notice${error ? ' error' : ''}`));
}
async function api(path, body, signal) {
  let response;
  try {
    response = await fetch(`/api/${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body), signal
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('The local studio is unavailable. Start python server.py and open http://127.0.0.1:8000.');
  }
  const data = await response.json().catch(() => { throw new Error('Open this page through the local Python server, not a static file server.'); });
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}
function download(name, value, type) {
  const url = URL.createObjectURL(new Blob([value], { type }));
  const link = node('a');
  link.href = url; link.download = name;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function fileData(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Could not read the selected file.'));
    reader.readAsDataURL(file);
  });
}
async function refreshStatus() {
  try {
    status = await api('status');
    const ready = Object.values(status.services).filter(Boolean).length;
    $('#connectionStatus').textContent = `${ready} of 4 services ready · local server connected`;
  } catch (error) {
    status = null;
    $('#connectionStatus').textContent = 'Start the local server to connect your tools';
  }
  return status;
}
function openWorkspace(id) {
  cleanup(); cleanup = () => {}; lifecycle++;
  content.replaceChildren();
  const tool = tools.find(item => item.id === id);
  $('#workspaceTitle').textContent = tool ? tool.title : id === 'status' ? 'Your workspace, at a glance.' : 'A studio for your curiosity.';
  $('#workspaceEyebrow').textContent = tool ? `EXPERIMENT 0${tools.indexOf(tool) + 1} / ${tool.short.toUpperCase()}` : 'FORMA / THE WORKSHOP STUDIO';
  if (!workspace.open) workspace.showModal();
  if (tool) {
    const tabs = node('nav', undefined, 'tool-tabs');
    tabs.setAttribute('aria-label', 'Choose experiment');
    tools.forEach(item => {
      const button = node('button', item.short, item.id === id ? 'active' : '');
      button.type = 'button'; button.dataset.open = item.id;
      button.setAttribute('aria-current', item.id === id ? 'page' : 'false');
      tabs.append(button);
    });
    content.append(tabs);
  }
  if (id === 'prices') renderPrices();
  else if (id === 'voice') renderVoice();
  else if (id === 'documents') renderDocuments();
  else if (id === 'hands') renderHands();
  else if (id === 'status') renderStatus();
  else renderIntro();
}
workspace.addEventListener('close', () => { cleanup(); cleanup = () => {}; lifecycle++; });
$('#closeWorkspace').addEventListener('click', () => workspace.close());
// Only close a backdrop click, not a click in a dialog's padding or scrollbar.
for (const dialog of [workspace, $('#searchDialog')]) {
  dialog.addEventListener('click', event => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
  });
}
document.addEventListener('click', event => {
  const button = event.target.closest('[data-open]');
  if (button) { if ($('#searchDialog').open) $('#searchDialog').close(); openWorkspace(button.dataset.open); }
});
function renderPrices() {
  content.insertAdjacentHTML('beforeend', `<p class="tool-description">A clearer view of the same product. Add up to five permitted public product pages with their CSS selectors. Compare only the same product and currency; shipping and stock are not included.</p>
    <form id="priceForm"><div class="form-grid"><div class="field"><label for="siteName">Store name</label><input id="siteName" name="site" placeholder="My permitted store" maxlength="100" required></div><div class="field"><label for="currency">Currency</label><input id="currency" name="currency" placeholder="INR" value="INR" pattern="[A-Za-z]{3}" maxlength="3" required></div></div>
    <div class="field"><label for="productUrl">Product page URL</label><input id="productUrl" name="url" type="url" placeholder="https://example.com/product" required></div><div class="form-grid"><div class="field"><label for="nameSelector">Product name CSS selector</label><input id="nameSelector" name="name_selector" value="h1" required></div><div class="field"><label for="priceSelector">Price CSS selector</label><input id="priceSelector" name="price_selector" placeholder=".product-price" required></div></div><button class="quiet-button" type="submit">+ Add product page</button></form>
    <div id="priceItems" class="item-list"></div><div class="form-actions"><button id="comparePrices" class="pill dark">Compare prices ${icon('arrow')}</button><button id="exportPrices" class="quiet-button">Export CSV</button></div><p class="small-print">Use only sites that permit scraping. Respect terms, robots.txt, and rate limits. Some stores require JavaScript or block automated access; this studio does not bypass those protections. Requests go from your local server to the submitted sites.</p><div id="priceOutput" class="result-area" role="status" aria-live="polite"></div>`);
  const output = $('#priceOutput');
  const runButton = $('#comparePrices');
  const exportButton = $('#exportPrices');
  let running = false;
  const controller = new AbortController();
  cleanup = () => controller.abort();
  function list() {
    const listElement = $('#priceItems'); listElement.replaceChildren();
    priceItems.forEach((item, index) => {
      const row = node('div', undefined, 'configured-item');
      const label = node('span', `${index + 1}. ${item.site} · ${item.currency}`);
      label.append(node('small', item.url));
      const remove = node('button', '×'); remove.type = 'button';
      remove.setAttribute('aria-label', `Remove ${item.site}`);
      remove.disabled = running;
      remove.onclick = () => { priceItems.splice(index, 1); list(); };
      row.append(label, remove); listElement.append(row);
    });
    runButton.disabled = !priceItems.length || running;
    exportButton.disabled = !priceResults.length || running;
  }
  $('#priceForm').addEventListener('submit', event => {
    event.preventDefault();
    if (running) return;
    if (priceItems.length >= 5) return toast('Keep each comparison to five pages or fewer.');
    const item = Object.fromEntries(new FormData(event.target));
    if (!['https:', 'http:'].includes(new URL(item.url).protocol)) return toast('Use an HTTP or HTTPS product page.');
    for (const key of Object.keys(item)) item[key] = item[key].trim();
    item.currency = item.currency.toUpperCase();
    priceItems.push(item); list();
    $('#productUrl').value = ''; $('#siteName').focus();
  });
  runButton.onclick = async () => {
    running = true; list(); notice(output, 'Reading product pages… Please allow a few seconds per store.');
    try {
      const data = await api('prices', { items: priceItems }, controller.signal);
      priceResults = data.results; showPriceResults(output);
    } catch (error) { if (error.name !== 'AbortError') notice(output, error.message, true); }
    finally { running = false; if (!controller.signal.aborted) list(); }
  };
  exportButton.onclick = () => {
    const fields = ['site', 'product', 'price_text', 'price_value', 'currency', 'url', 'status'];
    // Prevent spreadsheet formula evaluation of scraped, untrusted cells.
    const cell = value => { let text = String(value ?? ''); if (/^[\s]*[=+@-]/.test(text)) text = `'${text}`; return `"${text.replaceAll('"', '""')}"`; };
    download('forma-price-comparison.csv', '\ufeff' + [fields, ...priceResults.map(item => fields.map(key => item[key]))].map(row => row.map(cell).join(',')).join('\r\n'), 'text/csv;charset=utf-8');
  };
  list(); if (priceResults.length) showPriceResults(output);
}
function showPriceResults(output) {
  output.replaceChildren();
  const wrap = node('div', undefined, 'table-wrap');
  const table = node('table');
  const header = node('tr'); ['Store / product', 'Price', 'Result'].forEach(text => header.append(node('th', text)));
  const thead = node('thead'); thead.append(header); table.append(thead);
  const tbody = node('tbody');
  priceResults.forEach(item => {
    const row = node('tr'); const site = node('td');
    const link = node('a', item.site || 'Product page');
    try { const url = new URL(item.url); if (['http:', 'https:'].includes(url.protocol)) { link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; } } catch { /* Malformed result URLs stay non-navigable. */ }
    site.append(link, node('small', item.product || 'No product name extracted'));
    row.append(site, node('td', `${item.currency || ''} ${item.price_value || item.price_text || '—'}`), node('td', item.status));
    tbody.append(row);
  });
  table.append(tbody); wrap.append(table); output.append(wrap);
}
function renderVoice() {
  content.insertAdjacentHTML('beforeend', `<p class="tool-description">A space to think out loud. Type a question or use your browser’s microphone. Text and conversation history are sent to Groq; your API key stays on the local server.</p><div class="speech-controls"><button id="listenButton" class="quiet-button">${icon('mic')} Use microphone</button><label><input id="speakReplies" type="checkbox"> Read replies aloud</label><button id="clearConversation" class="quiet-button">Clear chat</button></div><p id="speechStatus" class="small-print"></p><div class="chat-log" id="chatLog" role="log" aria-label="Conversation" aria-live="polite"></div><form class="chat-form" id="chatForm"><label class="skip-link" for="chatInput">Your message</label><input id="chatInput" placeholder="What are you curious about?" maxlength="6000" required autocomplete="off"><button class="pill dark" type="submit">Send ↗</button></form><div id="chatError" role="status"></div>`);
  const log = $('#chatLog'); const form = $('#chatForm'); const input = $('#chatInput'); const errorArea = $('#chatError'); const speechStatus = $('#speechStatus');
  const controller = new AbortController(); let recognition = null; let pending = false;
  function appendMessage(role, text) {
    const message = node('div', undefined, `message ${role}`);
    message.append(node('strong', role === 'user' ? 'YOU' : 'FORMA'), document.createTextNode(text));
    log.append(message); log.scrollTop = log.scrollHeight;
  }
  if (conversation.length) conversation.forEach(item => appendMessage(item.role, item.content));
  else appendMessage('assistant', 'Hello, curious mind. Ask me about code, AI, or an idea you’d like to explore.');
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) { $('#listenButton').disabled = true; speechStatus.textContent = 'Speech recognition is not supported in this browser. Text chat is always available. Try Chrome or Edge for microphone input.'; }
  else {
    recognition = new SpeechRecognition(); recognition.lang = 'en-US'; recognition.interimResults = false;
    recognition.onresult = event => { input.value = event.results[0][0].transcript; speechStatus.textContent = 'Transcribed. Review your words, then press Send.'; input.focus(); };
    recognition.onerror = event => { speechStatus.textContent = `Microphone: ${event.error}. Check permissions or type your question instead.`; };
    recognition.onend = () => { $('#listenButton', content)?.removeAttribute('disabled'); };
    $('#listenButton').onclick = () => { try { recognition.start(); $('#listenButton').disabled = true; speechStatus.textContent = 'Listening… Your browser’s speech provider may process audio online.'; } catch { speechStatus.textContent = 'Microphone is already listening. Please wait.'; } };
  }
  if (!('speechSynthesis' in window)) { $('#speakReplies').disabled = true; }
  $('#clearConversation').onclick = () => { if (pending) return; conversation.length = 0; log.replaceChildren(); window.speechSynthesis?.cancel(); appendMessage('assistant', 'A fresh start. What would you like to explore?'); };
  form.onsubmit = async event => {
    event.preventDefault(); const message = input.value.trim(); if (!message || pending) return;
    recognition?.abort(); pending = true; $('button', form).disabled = true; $('#clearConversation').disabled = true;
    appendMessage('user', message); input.value = ''; notice(errorArea, 'Thinking…');
    try {
      const data = await api('chat', { message, history: conversation.slice(-12) }, controller.signal);
      conversation.push({ role: 'user', content: message }, { role: 'assistant', content: data.answer });
      if (conversation.length > 24) conversation.splice(0, conversation.length - 24);
      appendMessage('assistant', data.answer); errorArea.replaceChildren();
      if ($('#speakReplies').checked && window.speechSynthesis) { const utterance = new SpeechSynthesisUtterance(data.answer); utterance.lang = 'en-US'; window.speechSynthesis.speak(utterance); }
    } catch (error) { if (error.name !== 'AbortError') { notice(errorArea, error.message, true); input.value = message; } }
    finally { pending = false; if (!controller.signal.aborted) { $('button', form).disabled = false; $('#clearConversation').disabled = false; input.focus(); } }
  };
  cleanup = () => { controller.abort(); if (recognition) { recognition.onend = null; recognition.abort(); } window.speechSynthesis?.cancel(); };
}
function renderDocuments() {
  content.insertAdjacentHTML('beforeend', `<p class="tool-description">Less searching, more understanding. Upload a text-based PDF or UTF-8 TXT file. Local embeddings retrieve relevant passages; only your question and retrieved context go to Groq.</p><div class="upload-zone"><label for="documentFile">Give your knowledge a place to land.</label><p>PDF or TXT · maximum 8 MB · scanned PDFs need OCR first</p><input id="documentFile" type="file" accept=".pdf,.txt,application/pdf,text/plain"></div><div id="documentStatus" role="status" aria-live="polite"></div><form id="questionForm"><div class="field"><label for="documentQuestion">Ask something about your document</label><input id="documentQuestion" placeholder="What are the main takeaways?" required maxlength="6000"></div><button id="askDocument" type="submit" class="pill dark" disabled>Find an answer ${icon('arrow')}</button></form><div id="documentAnswer" class="result-area" aria-live="polite"></div><p class="small-print">Documents are held in local server memory, not saved to disk. Restarting the server clears them. The first upload may take longer while the embedding model downloads. Generated answers can be wrong: check the source passages.</p>`);
  const controller = new AbortController(); cleanup = () => controller.abort();
  const output = $('#documentStatus'); const answer = $('#documentAnswer'); const ask = $('#askDocument'); const upload = $('#documentFile');
  function showSession() { if (documentSession) { notice(output, `${documentSession.name} · ${documentSession.chunks} searchable chunks · ready for your questions`); ask.disabled = false; } }
  showSession();
  upload.onchange = async () => {
    const file = upload.files[0]; if (!file) return;
    if (!/\.(pdf|txt)$/i.test(file.name) || file.size > 8 * 1024 * 1024 || !file.size) { notice(output, 'Choose a non-empty PDF or TXT file smaller than 8 MB.', true); upload.value = ''; return; }
    ask.disabled = true; upload.disabled = true; documentSession = null; answer.replaceChildren();
    notice(output, 'Reading your document and building its semantic index… The first model download may take several minutes.');
    try {
      const data = await fileData(file);
      if (controller.signal.aborted) return;
      documentSession = await api('documents', { name: file.name, content: data.split(',')[1] }, controller.signal);
      showSession();
      if (documentSession.preview) {
        const preview = node('details', undefined, 'source-card');
        preview.append(node('summary', 'Preview the first document chunk'), node('p', documentSession.preview)); output.append(preview);
      }
    } catch (error) { if (error.name !== 'AbortError') notice(output, error.message, true); }
    finally { if (!controller.signal.aborted) { upload.disabled = false; upload.value = ''; } }
  };
  $('#questionForm').onsubmit = async event => {
    event.preventDefault(); const question = $('#documentQuestion').value.trim(); if (!question || !documentSession || ask.disabled) return;
    ask.disabled = true; upload.disabled = true; notice(answer, 'Finding relevant passages and composing a grounded answer…');
    try {
      const data = await api('ask', { id: documentSession.id, question }, controller.signal);
      answer.replaceChildren(node('h3', 'A little more clarity.'));
      answer.append(node('div', data.answer, 'message'));
      for (const source of data.sources) {
        const details = node('details', undefined, 'source-card');
        details.append(node('summary', `Source chunk ${source.number} · similarity ${Number(source.score).toFixed(3)}`), node('p', source.text));
        answer.append(details);
      }
    } catch (error) { if (error.name !== 'AbortError') notice(answer, error.message, true); }
    finally { if (!controller.signal.aborted) { ask.disabled = false; upload.disabled = false; } }
  };
}
function renderHands() {
  content.insertAdjacentHTML('beforeend', `<p class="tool-description">Look a little closer. Detect hand landmarks in a photo or a single webcam frame. Images are processed by your local Python server; camera access is requested only when you choose it.</p><div class="camera-stage" id="cameraStage"><div class="camera-placeholder">${icon('hand')}Choose a photo or start your camera.</div></div><div class="form-actions"><button id="startCamera" class="pill dark">Start camera ${icon('mic')}</button><button id="captureHand" class="quiet-button" disabled>Detect this frame</button><button id="stopCamera" class="quiet-button" disabled>Stop camera</button></div><div class="field"><label for="handImage">Or choose a hand photo (JPG, PNG, WebP · up to 8 MB)</label><input id="handImage" type="file" accept="image/jpeg,image/png,image/webp"></div><div id="handStatus" role="status" aria-live="polite"></div><a class="text-link" href="/api/notebook" download>Prefer video processing? Download the Colab notebook ↗</a><p class="small-print">This is a frame-by-frame experiment, not continuous tracking. Each detection returns up to two hands with 21 landmarks. Accuracy varies with lighting, framing, and occlusion. The original Colab workflow supports uploaded videos.</p>`);
  const stage = $('#cameraStage'); const output = $('#handStatus'); const start = $('#startCamera'); const capture = $('#captureHand'); const stop = $('#stopCamera'); const upload = $('#handImage');
  let stream = null; let video = null; let busy = false; let stopped = false;
  const controller = new AbortController();
  const edges = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
  function stopStream() { stream?.getTracks().forEach(track => track.stop()); stream = null; if (video) video.srcObject = null; video = null; capture.disabled = true; stop.disabled = true; start.disabled = false; }
  cleanup = () => { stopped = true; controller.abort(); stopStream(); };
  stop.onclick = () => { stopStream(); notice(output, 'Camera stopped. Your camera is no longer in use.'); };
  start.onclick = async () => {
    if (!navigator.mediaDevices?.getUserMedia) return notice(output, 'Camera access needs localhost or HTTPS and a supported browser. You can upload a photo instead.', true);
    start.disabled = true;
    try {
      const cameraStream = await navigator.mediaDevices.getUserMedia({ video: { width: 960, height: 720 }, audio: false });
      if (stopped) { cameraStream.getTracks().forEach(track => track.stop()); return; }
      stream = cameraStream; video = node('video'); video.autoplay = true; video.playsInline = true; video.muted = true; video.srcObject = stream;
      stage.replaceChildren(video); await video.play();
      if (stopped) return;
      capture.disabled = false; stop.disabled = false; notice(output, 'Camera ready. Hold your hand in view, then choose “Detect this frame”.');
    } catch (error) { stopStream(); if (!stopped) notice(output, `Could not start the camera: ${error.message}. Try a photo instead.`, true); }
  };
  async function detect(canvas) {
    if (busy) return; busy = true; capture.disabled = true; upload.disabled = true;
    notice(output, 'Looking for hand landmarks…');
    try {
      const data = await api('hands', { image: canvas.toDataURL('image/jpeg', .85) }, controller.signal);
      const ctx = canvas.getContext('2d');
      for (const hand of data.hands) {
        const points = hand.landmarks;
        ctx.strokeStyle = '#e4edbc'; ctx.lineWidth = Math.max(2, canvas.width / 400);
        edges.forEach(([a,b]) => { ctx.beginPath(); ctx.moveTo(points[a].x * canvas.width, points[a].y * canvas.height); ctx.lineTo(points[b].x * canvas.width, points[b].y * canvas.height); ctx.stroke(); });
        points.forEach(point => { ctx.beginPath(); ctx.arc(point.x * canvas.width, point.y * canvas.height, Math.max(3, canvas.width / 180), 0, Math.PI * 2); ctx.fillStyle = '#e5bf72'; ctx.fill(); });
      }
      stage.replaceChildren(canvas);
      notice(output, data.hands.length ? `${data.hands.length} hand${data.hands.length > 1 ? 's' : ''} detected · ${data.hands.map(hand => hand.handedness).join(' / ')} · 21 landmarks per hand` : 'No hands detected. Try brighter lighting, less occlusion, or move your hand further into the frame.');
    } catch (error) { if (error.name !== 'AbortError') notice(output, error.message, true); }
    finally { busy = false; if (!stopped) { capture.disabled = !stream; upload.disabled = false; } }
  }
  function fitCanvas(image, width, height) {
    const scale = Math.min(1, 1280 / Math.max(width, height));
    const canvas = node('canvas'); canvas.width = Math.round(width * scale); canvas.height = Math.round(height * scale);
    canvas.setAttribute('aria-label', 'Hand image with detected landmark overlay'); canvas.setAttribute('role', 'img');
    canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height); return canvas;
  }
  capture.onclick = () => { if (video?.videoWidth && !busy) detect(fitCanvas(video, video.videoWidth, video.videoHeight)); };
  upload.onchange = async () => {
    const file = upload.files[0]; if (!file) return;
    if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size > 8 * 1024 * 1024) return notice(output, 'Choose a JPG, PNG, or WebP photo smaller than 8 MB.', true);
    stopStream();
    try {
      const bitmap = await createImageBitmap(file);
      if (stopped) { bitmap.close(); return; }
      const canvas = fitCanvas(bitmap, bitmap.width, bitmap.height); bitmap.close(); stage.replaceChildren(canvas); await detect(canvas);
    } catch (error) { if (!stopped) notice(output, `Could not read the image: ${error.message}`, true); }
    finally { upload.value = ''; }
  };
}
function renderIntro() {
  content.append(node('p', 'Four independent Python experiments, brought together in a thoughtfully designed local workspace. Start anywhere. Learn by changing the inputs, examining the outputs, and understanding the limitations.', 'tool-description'));
  const grid = node('div', undefined, 'intro-grid');
  tools.forEach((tool, index) => {
    const button = node('button', undefined, 'intro-card'); button.dataset.open = tool.id;
    button.innerHTML = icon(tool.icon); button.append(node('p', `DAY 0${index + 1}`, 'eyebrow'), node('h3', tool.short), node('p', tool.description)); grid.append(button);
  });
  content.append(grid, node('p', 'Start the server with python server.py. Scraping needs permitted websites; chat and document answers need GROQ_API_KEY in your root .env. Hand detection and document search require their local Python dependencies. Nothing here trains a new model.', 'notice'));
  const button = node('button', 'Check setup & service status ↗', 'quiet-button'); button.dataset.open = 'status'; content.append(button);
}
async function renderStatus() {
  const ticket = lifecycle; const area = node('div'); content.append(area); notice(area, 'Checking local services…');
  const result = await refreshStatus(); if (ticket !== lifecycle) return;
  area.replaceChildren();
  if (!result) { notice(area, 'The local server is not connected. Run python server.py from the project root, then open http://127.0.0.1:8000.', true); return; }
  tools.forEach(tool => { const row = node('div', undefined, 'service-row'); row.append(node('span', tool.short), node('span', result.services[tool.id] ? 'Ready to try' : 'Setup needed', 'service-state')); area.append(row); });
  area.append(node('p', `Groq key: ${result.key_configured ? 'configured on server' : 'not configured'}. Model: ${result.model}. Readiness checks detect packages and configuration; they do not verify API credentials, download models, or perform inference.`, 'notice'));
  area.append(node('p', 'Use Python 3.10 or 3.11. Install requirements-web.txt in a virtual environment. Set GROQ_API_KEY in a root .env file and restart the server. Sentence-transformer models download on first document upload. Browser speech support varies.', 'small-print'));
}

function setFeature(index) {
  feature = (index + tools.length) % tools.length; const tool = tools[feature];
  $('#featureTitle').textContent = tool.title; $('#featureDescription').textContent = tool.description;
  $('#featureCount').textContent = `0${feature + 1} / 04`;
  $('#featureLaunch').textContent = `Try ${tool.short.toLowerCase()} ↗`; $('#featureLaunch').dataset.open = tool.id;
  $('.doc-art').innerHTML = icon(tool.icon); $('.doc-art').append(node('span', tool.short));
  $$('.slide-dots button').forEach((button, i) => { button.classList.toggle('active', i === feature); button.setAttribute('aria-pressed', String(i === feature)); });
}
$('#previousFeature').onclick = () => setFeature(feature - 1);
$('#nextFeature').onclick = () => setFeature(feature + 1);
$$('[data-slide]').forEach(button => button.onclick = () => setFeature(Number(button.dataset.slide)));
setFeature(3);
$$('[data-filter]').forEach(button => button.onclick = () => {
  activeFilter = button.dataset.filter;
  $$('[data-filter]').forEach(item => { const active = item === button; item.classList.toggle('active', active); item.setAttribute('aria-pressed', String(active)); });
  $$('.experiment-card').forEach(card => { card.hidden = activeFilter !== 'all' && card.dataset.category !== activeFilter; });
});
for (const id of ['tourButton', 'introButton', 'journeyIntro']) $(`#${id}`).onclick = () => openWorkspace('intro');
$('#statusButton').onclick = () => openWorkspace('status');
try { if (localStorage.getItem('forma-theme') === 'dark') document.body.classList.add('dark-theme'); } catch { /* Storage can be restricted in private or file contexts. */ }
$('#themeToggle').setAttribute('aria-pressed', String(document.body.classList.contains('dark-theme')));
$('#themeToggle').onclick = () => {
  const dark = document.body.classList.toggle('dark-theme'); $('#themeToggle').setAttribute('aria-pressed', String(dark));
  try { localStorage.setItem('forma-theme', dark ? 'dark' : 'light'); } catch { /* Theme still works without persistence. */ }
};
const searchDialog = $('#searchDialog');
function searchExperiments() {
  const query = $('#experimentSearch').value.trim().toLowerCase(); const results = $('#searchResults'); results.replaceChildren();
  const matches = tools.filter(tool => `${tool.short} ${tool.title} ${tool.keywords}`.toLowerCase().includes(query));
  matches.forEach(tool => { const button = node('button'); button.dataset.open = tool.id; button.innerHTML = icon(tool.icon); const label = node('span', tool.short); label.append(node('small', tool.title)); button.append(label, node('span', '↗')); results.append(button); });
  if (!matches.length) results.append(node('p', 'No matches yet. Try “voice”, “PDF”, “web”, or “vision”.', 'notice'));
}
$$('.search-open').forEach(button => button.onclick = () => { searchDialog.showModal(); searchExperiments(); $('#experimentSearch').focus(); });
$('#experimentSearch').oninput = searchExperiments;
$('#closeSearch').onclick = () => searchDialog.close();
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => { for (const entry of entries) { if (!entry.isIntersecting) continue; $$('.top-nav a').forEach(link => { const active = link.hash === `#${entry.target.id}`; link.classList.toggle('active', active); if (active) link.setAttribute('aria-current', 'location'); else link.removeAttribute('aria-current'); }); } }, { rootMargin: '-10% 0px -60% 0px', threshold: 0 });
  $$('main>section').forEach(section => observer.observe(section));
}
refreshStatus();
