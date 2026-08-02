/** Shared API helpers. Amounts from the API are always integer paise. */
(function (global) {
  const USER_KEY = "ea_user_id";

  function getUserId() {
    const el = document.getElementById("userId");
    if (el && el.value) return el.value;
    return localStorage.getItem(USER_KEY) || "1";
  }

  function setUserId(id) {
    localStorage.setItem(USER_KEY, String(id));
    const el = document.getElementById("userId");
    if (el) el.value = String(id);
  }

  function bindUserIdInput() {
    const el = document.getElementById("userId");
    if (!el) return;
    el.value = getUserId();
    el.addEventListener("change", () => setUserId(el.value));
  }

  function headers(extra = {}) {
    return { "X-User-Id": getUserId(), ...extra };
  }

  function rupees(paise) {
    return (
      "₹" +
      (Number(paise) / 100).toLocaleString("en-IN", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
      })
    );
  }

  function toPaise(rupeeInput) {
    return Math.round(Number(rupeeInput) * 100);
  }

  async function api(path, options = {}) {
    const res = await fetch(path, options);
    const text = await res.text();
    let data;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }
    if (!res.ok) {
      const detail =
        typeof data === "object" && data
          ? data.detail || JSON.stringify(data)
          : text || res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  global.EA = { getUserId, setUserId, bindUserIdInput, headers, rupees, toPaise, api };
})(window);
