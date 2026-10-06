const els = {
  btn: document.getElementById("btn"),
  dot: document.getElementById("dot"),
  statusPill: document.getElementById("statusPill"),
  statusText: document.getElementById("statusText"),
  transcriptBody: document.getElementById("transcriptBody"),
  charCount: document.getElementById("charCount"),
  bcIntent: document.getElementById("bcIntent"),
  bcAction: document.getElementById("bcAction"),
  bcWarning: document.getElementById("bcWarning"),
  refreshBtn: document.getElementById("refreshBtn"),
};

let ws = null;
let audioCtx = null;
let mediaStream = null;
let processor = null;
let running = false;

let finalizedText = "";
let partialText = "";

function render() {
  const total = (finalizedText + partialText).length;
  els.charCount.textContent = total + " karakter";

  if (!finalizedText && !partialText) {
    els.transcriptBody.innerHTML = '<span class="placeholder">Mikrofonu başlatınca konuşma burada belirecek...</span>';
    return;
  }
  const esc = s => s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  let html = "";
  if (finalizedText) html += '<span class="final-text">' + esc(finalizedText) + "</span>";
  if (partialText)   html += '<span class="partial-text"> ' + esc(partialText) + "</span>";
  els.transcriptBody.innerHTML = html;
  els.transcriptBody.scrollTop = els.transcriptBody.scrollHeight;
}

/* --- Battle Card güncellemesi: flip animasyonu ile --- */
function setBattleCard(bc) {
  const newValues = [
    (bc && bc.intent)  || "Henüz analiz yok",
    (bc && bc.action)  || "Henüz analiz yok",
    (bc && bc.warning) || "Henüz analiz yok",
  ];
  const bodies = [els.bcIntent, els.bcAction, els.bcWarning];
  const cards  = bodies.map(el => el.closest('.bc-card'));

  // Her kart için staggered (kademeli) flip
  cards.forEach((card, i) => {
    if (!card) return;

    // Kademeli başlama: 0ms, 120ms, 240ms
    const delay = i * 120;

    setTimeout(() => {
      // Flip animasyonunu başlat
      card.classList.add('flipping');

      // Animasyonun tam ortasında metni değiştir (kart 180° dönmüşken görünmez)
      setTimeout(() => {
        bodies[i].textContent = newValues[i];
      }, 450); // 900ms animasyonun tam yarısı

      // Animasyon bitince class'ı kaldır
      setTimeout(() => {
        card.classList.remove('flipping');
      }, 900);
    }, delay);
  });
}

function setStatus(text, live) {
  els.statusText.textContent = text;
  els.statusPill.classList.toggle("live", !!live);
}

function stopAll() {
  running = false;
  if (processor) { try { processor.disconnect(); } catch(e){} processor = null; }
  if (audioCtx)  { try { audioCtx.close(); } catch(e){} audioCtx = null; }
  if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
  if (ws) { try { ws.close(); } catch(e){} ws = null; }
}

async function start() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });
  } catch (e) {
    alert("Mikrofona erişilemedi: " + e.message);
    return;
  }

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(proto + "//" + location.host + "/ws");
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    setStatus("Dinleniyor", true);
    startAudio();
    running = true;
    els.btn.textContent = "Durdur";
    els.btn.classList.add("stop");
  };

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);

      if (msg.type === "error") {
        console.error("Sunucu hatası:", msg.msg);
        return;
      }

      if (msg.type === "stt") {
        if (msg.final) {
          finalizedText += (finalizedText ? " " : "") + msg.text;
          partialText = "";
        } else {
          partialText = msg.text;
        }
        render();
      }

      if (msg.type === "battle_card") {
        setBattleCard(msg.data);
      }
    } catch (e) { console.error(e); }
  };

  ws.onclose = () => setStatus("Bağlantı kapandı", false);
  ws.onerror = (e) => { console.error("WS:", e); setStatus("Hata", false); };
}

function startAudio() {
  try {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
  } catch (e) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }

  const source = audioCtx.createMediaStreamSource(mediaStream);
  processor = audioCtx.createScriptProcessor(4096, 1, 1);
  source.connect(processor);
  processor.connect(audioCtx.destination);

  processor.onaudioprocess = (e) => {
    if (!running || !ws || ws.readyState !== WebSocket.OPEN) return;
    const input = e.inputBuffer.getChannelData(0);
    const pcm16 = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    const actualRate = audioCtx.sampleRate;
    if (actualRate !== 16000) {
      const ratio = actualRate / 16000;
      const newLen = Math.floor(pcm16.length / ratio);
      const down = new Int16Array(newLen);
      for (let i = 0; i < newLen; i++) down[i] = pcm16[Math.floor(i * ratio)];
      ws.send(down.buffer);
    } else {
      ws.send(pcm16.buffer);
    }
  };
}

function stop() {
  stopAll();
  els.btn.textContent = "Başlat";
  els.btn.classList.remove("stop");
  setStatus("Durduruldu", false);
}

els.btn.onclick = () => running ? stop() : start();

els.refreshBtn.onclick = () => {
  els.refreshBtn.textContent = "⏳...";
  els.refreshBtn.disabled = true;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: "refresh_bc" }));
  }
  setTimeout(() => {
    els.refreshBtn.textContent = "🔄 Yenile";
    els.refreshBtn.disabled = false;
  }, 1000);
};