const $ = (s) => document.querySelector(s);

const STORAGE_KEY = 'countdown-widget-settings';

// ---- 持久化设置 ----
function loadSettings() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw) {
    try { return JSON.parse(raw); } catch { /* ignore */ }
  }
  return {};
}

function saveSettings(obj) {
  const existing = loadSettings();
  Object.assign(existing, obj);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(existing));
}

function applySettings(settings) {
  if (settings.targetDate) {
    $targetInput.value = settings.targetDate;
  }
  if (settings.textColor) {
    document.documentElement.style.setProperty('--text-color', settings.textColor);
    $textColorInput.value = settings.textColor;
  }
  if (settings.accentColor) {
    document.documentElement.style.setProperty('--accent-color', settings.accentColor);
    $accentColorInput.value = settings.accentColor;
  }
  if (settings.bgImage) {
    $bgLayer.style.backgroundImage = `url(${settings.bgImage})`;
  }
  if (settings.bgOpacity !== undefined) {
    document.documentElement.style.setProperty('--bg-opacity', settings.bgOpacity / 100);
    $bgOpacityInput.value = settings.bgOpacity;
  }
  if (settings.overlayOpacity !== undefined) {
    document.documentElement.style.setProperty('--overlay-opacity', settings.overlayOpacity / 100);
    $overlayOpacityInput.value = settings.overlayOpacity;
  }
  if (settings.widgetScale !== undefined) {
    document.documentElement.style.setProperty('--widget-scale', settings.widgetScale / 100);
    $scaleInput.value = settings.widgetScale;
  }
}

// ---- DOM ----
const $bgLayer = $('#bg-layer');
const $days = $('#days');
const $hours = $('#hours');
const $minutes = $('#minutes');
const $seconds = $('#seconds');
const $targetLabel = $('#target-label');
const $settingsPanel = $('#settings-panel');
const $targetInput = $('#input-target');
const $textColorInput = $('#input-text-color');
const $accentColorInput = $('#input-accent-color');
const $bgOpacityInput = $('#input-bg-opacity');
const $overlayOpacityInput = $('#input-overlay-opacity');
const $scaleInput = $('#input-scale');

// ---- 倒计时逻辑 ----
let targetDate = null;

function pad(n) {
  return String(n).padStart(2, '0');
}

function updateCountdown() {
  if (!targetDate) {
    $days.textContent = '--';
    $hours.textContent = '--';
    $minutes.textContent = '--';
    $seconds.textContent = '--';
    $targetLabel.textContent = '请在设置中设定目标日期';
    return;
  }

  const now = Date.now();
  const diff = targetDate.getTime() - now;

  if (diff <= 0) {
    $days.textContent = '00';
    $hours.textContent = '00';
    $minutes.textContent = '00';
    $seconds.textContent = '00';
    $targetLabel.textContent = '时间到！';
    return;
  }

  const totalSec = Math.floor(diff / 1000);
  const d = Math.floor(totalSec / 86400);
  const h = Math.floor((totalSec % 86400) / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;

  $days.textContent = pad(d);
  $hours.textContent = pad(h);
  $minutes.textContent = pad(m);
  $seconds.textContent = pad(s);

  const fmt = (n, unit) => n > 0 ? `${n}${unit}` : '';
  const parts = [fmt(d, '天'), fmt(h, '时'), fmt(m, '分'), fmt(s, '秒')].filter(Boolean);
  $targetLabel.textContent = `距离 ${targetDate.toLocaleString('zh-CN')} 还有 ${parts.join(' ')}`;
}

function setTarget(dateStr) {
  if (dateStr) {
    targetDate = new Date(dateStr);
    saveSettings({ targetDate: dateStr });
  } else {
    targetDate = null;
    saveSettings({ targetDate: null });
  }
  updateCountdown();
}

// ---- 设置面板 ----
$('#btn-settings').addEventListener('click', () => {
  $settingsPanel.classList.toggle('hidden');
});

$('#btn-close-settings').addEventListener('click', () => {
  $settingsPanel.classList.add('hidden');
});

$targetInput.addEventListener('change', () => {
  setTarget($targetInput.value || null);
});

$textColorInput.addEventListener('input', () => {
  const v = $textColorInput.value;
  document.documentElement.style.setProperty('--text-color', v);
  saveSettings({ textColor: v });
});

$accentColorInput.addEventListener('input', () => {
  const v = $accentColorInput.value;
  document.documentElement.style.setProperty('--accent-color', v);
  saveSettings({ accentColor: v });
});

$bgOpacityInput.addEventListener('input', () => {
  const v = parseInt($bgOpacityInput.value);
  document.documentElement.style.setProperty('--bg-opacity', v / 100);
  saveSettings({ bgOpacity: v });
});

$overlayOpacityInput.addEventListener('input', () => {
  const v = parseInt($overlayOpacityInput.value);
  document.documentElement.style.setProperty('--overlay-opacity', v / 100);
  saveSettings({ overlayOpacity: v });
});

$scaleInput.addEventListener('input', () => {
  const v = parseInt($scaleInput.value);
  document.documentElement.style.setProperty('--widget-scale', v / 100);
  saveSettings({ widgetScale: v });
});

// ---- 背景图片 ----
const $bgFileInput = $('#input-bg-file');

$('#btn-bg-select').addEventListener('click', () => {
  $bgFileInput.click();
});

$bgFileInput.addEventListener('change', () => {
  const file = $bgFileInput.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl = e.target.result;
    $bgLayer.style.backgroundImage = `url(${dataUrl})`;
    saveSettings({ bgImage: dataUrl });
  };
  reader.readAsDataURL(file);
});

$('#btn-bg-clear').addEventListener('click', () => {
  $bgLayer.style.backgroundImage = '';
  saveSettings({ bgImage: null });
});

// ---- 窗口控制 ----
$('#btn-close').addEventListener('click', () => {
  if (window.electronAPI) window.electronAPI.closeWindow();
});
$('#btn-min').addEventListener('click', () => {
  if (window.electronAPI) window.electronAPI.minimizeWindow();
});

let isPinned = false;
$('#btn-pin').addEventListener('click', async () => {
  isPinned = !isPinned;
  $('#btn-pin').textContent = isPinned ? '📌' : '📍';
  $('#btn-pin').style.opacity = isPinned ? '1' : '0.5';
  if (window.electronAPI) await window.electronAPI.setAlwaysOnTop(isPinned);
});

// ---- 右键菜单 ----
document.addEventListener('contextmenu', (e) => {
  e.preventDefault();
  showContextMenu(e.clientX, e.clientY);
});

document.addEventListener('click', () => {
  const menu = $('#context-menu');
  if (menu) menu.style.display = 'none';
});

function showContextMenu(x, y) {
  let menu = $('#context-menu');
  if (!menu) {
    menu = document.createElement('div');
    menu.id = 'context-menu';
    menu.innerHTML = `
      <div class="menu-item" data-action="settings">⚙ 设置</div>
      <div class="menu-item" data-action="pin">📌 切换置顶</div>
      <div class="menu-sep"></div>
      <div class="menu-item" data-action="close">✕ 退出</div>
    `;
    document.body.appendChild(menu);

    menu.addEventListener('click', (e) => {
      const item = e.target.closest('.menu-item');
      if (!item) return;
      const action = item.dataset.action;
      menu.style.display = 'none';
      if (action === 'settings') $settingsPanel.classList.remove('hidden');
      if (action === 'pin') $('#btn-pin').click();
      if (action === 'close' && window.electronAPI) window.electronAPI.closeWindow();
    });
  }
  menu.style.display = 'block';
  menu.style.left = Math.min(x, window.innerWidth - 160) + 'px';
  menu.style.top = Math.min(y, window.innerHeight - 140) + 'px';
}

// ---- 浏览器模式：隐藏桌面窗口专用按钮 ----
if (!window.electronAPI) {
  const btns = ['btn-pin', 'btn-min', 'btn-close'];
  btns.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
}

// ---- 初始化 ----
const settings = loadSettings();

// 默认目标：7天后
if (!settings.targetDate) {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  d.setHours(0, 0, 0, 0);
  settings.targetDate = d.toISOString().slice(0, 16);
}

applySettings(settings);

if (settings.targetDate) {
  setTarget(settings.targetDate);
} else {
  updateCountdown();
}

// 每秒刷新
setInterval(updateCountdown, 1000);
