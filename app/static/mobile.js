/* PortaCustodia · Mobile controls and local barcode scanner. No external services. */
(()=>{
  'use strict';
  if ('serviceWorker' in navigator && window.isSecureContext) {
    window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));
  }
  const input=document.querySelector('[data-scan-field]');
  const lookup=document.querySelector('[data-device-lookup]');
  const status=document.querySelector('[data-scan-status]');
  const panel=document.querySelector('[data-scanner-panel]');
  const video=document.querySelector('[data-scanner-video]');
  let stream=null, scanning=false;
  const report=(s)=>{ if(status)status.textContent=s; };
  const normalize=(s)=>String(s||'').trim();
  async function lookupDevice(value) {
    value=normalize(value);
    if(!value){report('Indique o escanee un número de serie o inventario.');return;}
    report('Consultando inventario…');
    try{
      const response=await fetch('/api/equipos/buscar?codigo='+encodeURIComponent(value),{credentials:'same-origin',cache:'no-store'});
      if(response.redirected && response.url.includes('/login')){report('La sesión ha caducado. Vuelva a identificarse.');return;}
      if(!response.ok){report('No ha sido posible consultar el inventario.');return;}
      const record=await response.json();
      if(!record.found){report('Código no encontrado. Compruebe si el fabricante tiene otro código de producto o servicio.');return;}
      report('Equipo '+record.asset_tag+' identificado. Abriendo ficha…');
      window.location.href='/equipos/'+record.id;
    } catch(_){report('Sin conexión. La consulta requiere acceso al servidor.');}
  }
  document.querySelector('[data-find-device]')?.addEventListener('click',()=>lookupDevice(lookup?.value));
  if(lookup){lookup.addEventListener('keydown',(e)=>{if(e.key==='Enter'){e.preventDefault();lookupDevice(lookup.value);}});}
  if(input && !lookup){input.addEventListener('keydown',(e)=>{if(e.key==='Enter'){e.preventDefault();report('Número de serie leído; compruebe la etiqueta y complete la ficha.');}});}
  function stop(){scanning=false; if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;} if(video)video.srcObject=null; if(panel)panel.hidden=true;}
  window.addEventListener('pagehide',stop);
  document.querySelector('[data-stop-scanner]')?.addEventListener('click',stop);
  async function start(){
    if(!input)return;
    if(!window.isSecureContext || !navigator.mediaDevices?.getUserMedia){report('La cámara requiere HTTPS y un navegador compatible. Use el lector Bluetooth/USB.');return;}
    if(!('BarcodeDetector' in window)){report('El navegador no permite leer códigos con la cámara. Use un lector USB/Bluetooth o escriba el número.');return;}
    try{
      const supported=await BarcodeDetector.getSupportedFormats();
      const formats=['code_128','code_39','code_93','ean_13','ean_8','itf','qr_code','data_matrix'].filter(f=>supported.includes(f));
      if(!formats.length){report('No hay formatos compatibles. Introduzca el número manualmente.');return;}
      const detector=new BarcodeDetector({formats});
      stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'},width:{ideal:1280}}});
      if(!video){stop();return;}
      video.srcObject=stream;
      if(panel)panel.hidden=false;
      await video.play();scanning=true;
      report('Enfoque el código de barras o QR de la etiqueta del equipo.');
      while(scanning){
        let codes=[];
        try{if(video.readyState>=2)codes=await detector.detect(video);}catch(_){/* try next frame */}
        if(codes.length){
          input.value=normalize(codes[0].rawValue); stop();
          if(lookup)await lookupDevice(input.value);
          else report('Código detectado: '+input.value+'. Verifique que es el número de serie.');
          break;
        }
        await new Promise(resolve=>setTimeout(resolve,220));
      }
    }catch(error){stop();report(error?.name==='NotAllowedError'?'No se ha autorizado la cámara. Active el permiso en el navegador.':'No se puede iniciar la cámara. Utilice el lector externo.');}
  }
  document.querySelectorAll('[data-scan-photo]').forEach(fileEl=>fileEl.addEventListener('change',async ()=>{
    const selected=fileEl.files?.[0];if(!selected)return;
    if(selected.size>6*1024*1024){report('La fotografía del código debe ocupar menos de 6 MB.');return;}
    const token=document.querySelector('meta[name="pc-csrf"]')?.content;
    if(!token){report('Debe iniciar sesión para escanear.');return;}
    const form=new FormData();form.set('photo',selected);form.set('csrf',token);
    report('Leyendo el código de la etiqueta…');
    try{
      const response=await fetch('/api/equipos/decodificar-codigo',{method:'POST',body:form,credentials:'same-origin',cache:'no-store'});
      const data=await response.json();
      if(!response.ok){report(data.error||'No se puede decodificar la etiqueta.');return;}
      if(!data.codes?.length){report('No se ha reconocido un código. Acerque la cámara y evite reflejos o introduzca el número manualmente.');return;}
      if(data.codes.length>1){report('Se encontraron varios códigos; consulte la etiqueta para distinguir el número de serie.');return;}
      if(input)input.value=data.codes[0].value;
      report('Código encontrado ('+data.codes[0].format+'): '+data.codes[0].value+'. Compruebe que corresponde al número de serie.');
      if(lookup)await lookupDevice(data.codes[0].value);
    }catch(_){report('No fue posible leer la foto. Compruebe la conexión con el servidor.');}
    finally{fileEl.value='';}
  }));
  document.querySelectorAll('[data-open-scanner]').forEach(btn=>btn.addEventListener('click',start));
  document.querySelectorAll('[data-photo-input]').forEach(el=>el.addEventListener('change',()=>{
    const box=el.closest('form')?.querySelector('[data-photo-preview]');if(!box)return;
    const file=el.files?.[0];box.replaceChildren();if(!file)return;
    const pic=document.createElement('img');pic.alt='Vista previa de la fotografía';pic.className='photo-preview';
    const local=URL.createObjectURL(file);pic.src=local;pic.onload=()=>URL.revokeObjectURL(local);box.append(pic);
  }));
})();