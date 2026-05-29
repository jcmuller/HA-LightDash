function st(){
  document.querySelectorAll(".tile-card").forEach(function(e){
    var s=e.querySelector(".entity-state"),t=e.querySelector(".toggle-input");
    if(s&&t){var o=s.textContent.trim()==="on";t.checked=o;e.classList.toggle("entity-on",o);e.classList.toggle("entity-off",!o);}
  });
  document.querySelectorAll(".entities-card .entity-row").forEach(function(e){
    var s=e.querySelector(".entity-state"),t=e.querySelector(".toggle-input");
    if(s&&t){var o=s.textContent.trim()==="on";t.checked=o;e.classList.toggle("entity-on",o);e.classList.toggle("entity-off",!o);}
  });
}
document.addEventListener("htmx:afterSwap",st);
document.addEventListener("htmx:sseMessage",st);
