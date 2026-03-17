(function () {
  const PORT = 8765;
  const url = location.href;
  const html = document.documentElement.outerHTML;

  fetch(`http://127.0.0.1:${PORT}/bookmarklet`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, html }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.status === "ok") {
        alert("Noble Shelfに送信しました！");
      } else {
        alert("エラー: " + JSON.stringify(data));
      }
    })
    .catch(() => {
      alert("Noble Shelfが起動していません。起動してからやり直してください。");
    });
})();

