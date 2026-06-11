// Symbol autocomplete for every <input data-autocomplete>.
// Picking a suggestion fills the input and dispatches "symbol-selected".
(function () {
    function attach(input) {
        const wrap = document.createElement("div");
        wrap.className = "ac-wrap";
        input.parentNode.insertBefore(wrap, input);
        wrap.appendChild(input);

        const list = document.createElement("div");
        list.className = "list-group ac-list shadow text-start";
        wrap.appendChild(list);

        let items = [];
        let active = -1;
        let timer = null;
        let lastQuery = "";

        function close() {
            list.innerHTML = "";
            list.style.display = "none";
            items = [];
            active = -1;
        }

        function pick(item) {
            input.value = item.symbol;
            close();
            input.dispatchEvent(new CustomEvent("symbol-selected", { detail: item, bubbles: true }));
        }

        function render() {
            list.innerHTML = "";
            items.forEach((item, i) => {
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "list-group-item list-group-item-action" + (i === active ? " active" : "");
                const sym = document.createElement("strong");
                sym.textContent = item.symbol;
                const name = document.createElement("span");
                name.className = "text-muted small ms-2";
                name.textContent = item.name;
                btn.append(sym, name);
                btn.addEventListener("mousedown", (e) => { e.preventDefault(); pick(item); });
                list.appendChild(btn);
            });
            list.style.display = items.length ? "block" : "none";
        }

        input.addEventListener("input", () => {
            const q = input.value.trim();
            clearTimeout(timer);
            if (q.length < 2) { close(); return; }
            timer = setTimeout(async () => {
                lastQuery = q;
                try {
                    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
                    if (!res.ok) return;
                    const data = await res.json();
                    if (q !== lastQuery) return; // a newer query is in flight
                    items = data;
                    active = -1;
                    render();
                } catch (e) { /* no suggestions when offline */ }
            }, 350);
        });

        input.addEventListener("keydown", (e) => {
            if (!items.length) return;
            if (e.key === "ArrowDown") { e.preventDefault(); active = (active + 1) % items.length; render(); }
            else if (e.key === "ArrowUp") { e.preventDefault(); active = (active - 1 + items.length) % items.length; render(); }
            else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(items[active]); }
            else if (e.key === "Escape") close();
        });

        input.addEventListener("blur", () => setTimeout(close, 150));
    }

    document.querySelectorAll("input[data-autocomplete]").forEach(attach);
})();
