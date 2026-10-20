
async function loadTodayCoffeeDeals() {
  const root = document.getElementById("todayCoffeeDeals");
  if (!root) return;

  root.innerHTML = "<p>正在載入今日咖啡優惠…</p>";

  try {
    const response = await fetch("./deals.json?ts=" + Date.now());
    if (!response.ok) throw new Error("無法讀取優惠資料");

    const data = await response.json();
    const today = new Date();
    const date = new Date(today.getTime() - today.getTimezoneOffset() * 60000)
      .toISOString().slice(0, 10);

    const deals = (data.deals || []).filter(d =>
      d.status === "active" &&
      d.start_date && d.end_date &&
      d.start_date <= date && date <= d.end_date
    );

    const esc = s => String(s || "").replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;",
      '"': "&quot;", "'": "&#39;"
    }[c]));

    if (!deals.length) {
      root.innerHTML =
        "<p>目前沒有能確認日期仍有效的優惠。請查看原文或官方活動頁；這不代表沒有優惠。</p>";
      return;
    }

    root.innerHTML = deals.map(d => `
      <article class="deal-card">
        <strong>${esc(d.store)}</strong>
        <p>${esc(d.offer)}</p>
        <small>活動日期：${esc(d.start_date)} 至 ${esc(d.end_date)}</small>
        <p><a href="${esc(d.article_url)}" target="_blank"
        rel="noopener noreferrer">查看優惠原文</a></p>
      </article>
    `).join("");
  } catch (error) {
    root.innerHTML = "<p>暫時無法載入優惠，請稍後再試。</p>";
  }
}

document.addEventListener("DOMContentLoaded", loadTodayCoffeeDeals);
