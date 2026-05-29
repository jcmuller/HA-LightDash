function uc(){
  document.querySelectorAll(".clock-digital").forEach(function(e){
    var o={
      hour:"2-digit",
      minute:"2-digit",
      timeZone:e.getAttribute("data-tz")||"Europe/London",
      hour12:e.getAttribute("data-fmt")!=="24"
    };
    if(e.getAttribute("data-sec"))o.second="2-digit";
    e.textContent=(new Intl.DateTimeFormat("en-GB",o)).format(new Date())
  })
}
setInterval(uc,30000);
document.addEventListener("DOMContentLoaded",uc);
