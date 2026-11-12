/* WebRTC and foreground chat control shared by the remote HTML and desktop React hosts.
   The bound request function always targets the chat selected at call creation. */
function createChatVoice(request, changed) {
  let closed = false, ready = false, pc, stream, channel, audio, timer, handshakeTimer;
  let pending = Promise.resolve(), consumed = -1;
  const fragments = [], seen = new Set(), delegations = new Set(), watching = new Map();
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

  function stop(error = '') {
    if (closed) return;
    closed = true;
    clearTimeout(timer);
    clearTimeout(handshakeTimer);
    window.removeEventListener('pagehide', leave);
    document.removeEventListener('visibilitychange', visibility);
    stream?.getTracks().forEach(track => track.stop());
    if (audio) { audio.pause(); audio.srcObject = null; audio.remove(); }
    if (channel?.readyState === 'open') {
      channel.send(JSON.stringify({type:'session.close'}));
      setTimeout(() => pc?.close(), 1200);
    } else pc?.close();
    changed('off', error);
  }
  function leave() { stop(); }
  function visibility() { if (document.hidden) stop(); }

  function append(type, id, content) {
    if (closed || !ready || channel?.readyState !== 'open') return;
    channel.send(JSON.stringify({type, event_id:crypto.randomUUID(), delegation_id:id, content}));
  }
  function say(id, text) { append('session.commentary.append', id, text); }
  function tellResult(id, status) {
    // Bound every append (provider limit 500 tokens), preserving the conclusion of long reports.
    const chars = Array.from(status.detail || '');
    for (let i = 0; i < chars.length; i += 100) {
      append('session.thinking.append', id, '작업 결과 자료: ' + chars.slice(i, i + 100).join(''));
    }
    const states = {running:'실행 중', failed:'실패', cancelled:'취소', interrupted:'중단', completed:'응답 도착', idle:'진행 중인 작업 없음'};
    say(id, '작업 상태: ' + (states[status.state] || status.state) +
      (chars.length ? '. 방금 받은 자료의 확인된 핵심만 한 문장으로 알려주세요.' : '. 추가로 확인한 결과는 없습니다.'));
  }
  async function poll() {
    for (const [turn, id] of watching) {
      const status = await request('/voice-state', 'GET', {turn_id:turn});
      if (closed) return;
      if (status.state !== 'running') {
        watching.delete(turn);
        tellResult(id, status);
      }
    }
    if (!closed) timer = setTimeout(() => poll().catch(failed), 1200);
  }
  function failed(error) { stop(error?.message || '음성 연결이 끊어졌습니다.'); }
  async function dispatch(id, offset) {
    // Delegations contain an offset and ID only. Give delayed transcript packets time to arrive.
    await delay(450);
    if (closed) return;
    const timeline = fragments.filter(f => f.start <= offset).sort((a,b) => a.start - b.start);
    const fresh = timeline.filter(f => f.user && f.start > consumed);
    // Use prior turns as context; only the latest speech group may initiate an action.
    const newest = [];
    for (const f of fresh) {
      const previous = newest.at(-1);
      if (previous && timeline.some(other => !other.user && other.start >= previous.end && other.end <= f.start)) newest.length = 0;
      newest.push(f);
    }
    if (!newest.length) { say(id,'명령을 확인하지 못했어요. 다시 말씀해 주세요.'); return; }
    const utterance = newest.map(f => f.text).join('').trim();
    if (!utterance || utterance.length > 2400) { say(id,'지시를 짧게 다시 말씀해 주세요.'); return; }
    const history = [];
    for (const f of timeline.filter(f => f.start < newest[0].start)) {
      if (history.at(-1)?.user === f.user) history.at(-1).text += f.text;
      else history.push({user:f.user, text:f.text});
    }
    const context = history.map(f => (f.user ? '사용자 ' : 'AI ') + f.text).join('\n').slice(-2400);
    consumed = offset;
    const state = await request('/voice-state', 'GET', {});
    const turn = state.state === 'running' ? state.turn_id : '';
    if (closed) return;
    const decision = await request('/voice-intent','POST',{utterance, context, turn_id:turn});
    if (closed) return;
    if (decision.kind === 'status') {
      const status = await request('/voice-state','GET',turn ? {turn_id:turn} : {});
      tellResult(id,status); return;
    }
    if (decision.kind === 'clarify') { say(id, Array.from(decision.message).slice(0,100).join('')); return; }
    if (decision.kind === 'new') {
      if (turn) { say(id,'이 대화에서 다른 작업을 수행 중입니다. 새 작업을 시작하려면 새 대화를 열어 주세요.'); return; }
      const result = await request('/messages','POST',{message:decision.message});
      watching.set(result.turn_id,id);
      append('session.thinking.append',id,'에이전트가 작업을 접수했다. 실행 결과는 아직 없다.');
    } else if (!turn) {
      say(id,'변경할 실행 중인 작업이 없습니다.');
    } else if (decision.kind === 'steer') {
      const receipt = await request('/steer','POST',{message:decision.message,turn_id:turn,request_id:id});
      if (receipt.accepted && !watching.has(turn)) watching.set(turn,id);
      say(id,receipt.accepted ? '추가 지시를 접수했습니다. 반영은 아직 확인되지 않았습니다.' : (receipt.reason || '추가 지시를 접수하지 못했습니다.'));
    } else if (decision.kind === 'cancel') {
      const result = await request('/cancel','POST',{turn_id:turn});
      say(id,result.cancelled ? '작업에 중단을 요청했습니다.' : '대상 작업이 이미 끝났습니다.');
    }
  }
  function event(data) {
    if (data.type === 'session.closed') { stop(); pc?.close(); return; }
    if (closed) return;
    if (data.type === 'error' || data.type === 'session.error') { failed(Error('OpenAI 음성 세션 오류: ' + (data.error?.code || '연결을 다시 시작해 주세요.'))); return; }
    if (data.type === 'session.started' && !ready) {
      ready = true; clearTimeout(handshakeTimer); changed('on','');
      poll().catch(failed); return;
    }
    if (!ready) return;
    if (data.type === 'session.input_transcript.delta' || data.type === 'session.output_transcript.delta') {
      if (data.event_id && seen.has(data.event_id)) return;
      if (data.event_id) seen.add(data.event_id);
      if (typeof data.delta !== 'string' || !Number.isFinite(data.start_ms)) return;
      fragments.push({text:data.delta,user:data.type === 'session.input_transcript.delta',start:data.start_ms,end:data.end_ms});
      if (fragments.length > 1200) fragments.shift();
    } else if (data.type === 'session.delegation.created' && data.delegation?.target === 'client') {
      const id = data.delegation.id;
      if (!id || delegations.has(id) || !Number.isFinite(data.offset_ms)) return;
      delegations.add(id);
      pending = pending.then(() => dispatch(id,data.offset_ms)).catch(error => {
        const message = error?.message || '요청 접수 여부를 확인하지 못했습니다.';
        if (!closed) { changed('on',message); say(id, Array.from(message).slice(0,100).join('')); }
      });
    }
  }
  async function start() {
    try {
      changed('starting','');
      if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection)
        throw Error('HTTPS로 원격런처를 열고 마이크 사용을 허용해 주세요.');
      window.addEventListener('pagehide', leave);
      document.addEventListener('visibilitychange', visibility);
      stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});
      if (closed) {stream.getTracks().forEach(track => track.stop()); return;}
      pc = new RTCPeerConnection();
      audio = document.createElement('audio'); audio.autoplay = true; audio.hidden = true; document.body.append(audio);
      pc.ontrack = e => {
        if (closed) return;
        audio.srcObject = e.streams[0] || new MediaStream([e.track]);
        audio.play().catch(() => failed(Error('음성 재생이 차단되었습니다. 다시 시작해 주세요.')));
      };
      pc.onconnectionstatechange = () => {
        if (['failed','disconnected','closed'].includes(pc.connectionState) && !closed) failed(Error('음성 연결이 끊어졌습니다.'));
      };
      for (const track of stream.getTracks()) pc.addTrack(track,stream);
      channel = pc.createDataChannel('oai-events');
      channel.onmessage = e => { try {event(JSON.parse(e.data));} catch {failed(Error('음성 서버 응답을 읽을 수 없습니다.'));} };
      channel.onclose = () => {if (!closed) failed(Error('음성 연결이 종료되었습니다.'));};
      handshakeTimer = setTimeout(() => failed(Error('음성 연결 시간이 초과되었습니다.')),35000);
      await pc.setLocalDescription(await pc.createOffer());
      const until = Date.now() + 5000;
      while (!closed && pc.iceGatheringState !== 'complete' && Date.now() < until) await delay(50);
      if (closed) return;
      const result = await request('/voice','POST',{sdp:pc.localDescription.sdp});
      if (!closed) await pc.setRemoteDescription({type:'answer',sdp:result.sdp});
    } catch(error) {
      failed(error.name === 'NotAllowedError' ? Error('마이크 권한을 허용해 주세요.') : error);
    }
  }
  return {start, stop};
}
/* --- ESM export (classic-script hosts omit only this tail) --- */
export {createChatVoice};
