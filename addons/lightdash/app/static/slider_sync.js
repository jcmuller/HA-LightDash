function ss(e){
  var s=e.detail.elt;
  if(!s||!s.classList.contains("entity-state"))return;
  var c=s.closest(".tile-card");
  if(!c)return;
  var r=c.querySelector(".feature-slider");
  if(!r)return;
  var eid=s.getAttribute("data-entity");
  if(!eid)return;
  fetch(STATE_API_URL+encodeURIComponent(eid)).then(function(resp){return resp.json()}).then(function(d){
    if(d&&d.attributes&&d.attributes.brightness){r.value=Math.round(d.attributes.brightness/255*100);}
  });
}
document.addEventListener("htmx:sseMessage",ss);
