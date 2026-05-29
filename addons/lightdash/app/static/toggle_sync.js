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

document.addEventListener("change",function(e){
  var i=e.target;
  if(!i.classList.contains("toggle-input"))return;
  var on=i.checked;
  var c=i.closest(".tile-card,.entity-row");
  if(c){c.classList.toggle("entity-on",on);c.classList.toggle("entity-off",!on);}
  var s=c&&c.querySelector(".entity-state");
  if(s){var t=s.textContent.trim().toLowerCase();if(t==="on"||t==="off")s.textContent=on?"on":"off";}
});
