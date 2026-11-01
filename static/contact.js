// The contact address is not in the page as text, so address harvesters that read HTML
// don't find it. The button holds it base64-encoded and reversed; a click turns it into a
// normal mailto link. People with JavaScript off get the LinkedIn link next to it.
document.addEventListener("click", (e) => {
  const b = e.target.closest("button.email-reveal");
  if (!b) return;
  const addr = [...atob(b.dataset.e)].reverse().join("");
  const a = document.createElement("a");
  a.href = "mailto:" + addr;
  a.textContent = addr;
  b.replaceWith(a);
  a.focus();
});
