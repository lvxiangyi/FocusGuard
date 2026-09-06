/* FocusGuard MVP 01 · local interaction prototype · no backend or AI calls. */
'use strict';
const LANGS = {zh:'中文',en:'English',ja:'日本語',ko:'한국어',fr:'Français',pt:'Português'};
// Column order: Chinese, English, Japanese, Korean, French, Portuguese.
const copy = {
workspace:['我的工作空间','MY WORKSPACE','ワークスペース','내 작업 공간','MON ESPACE','MEU ESPAÇO'],
focus:['专注','Focus','集中','집중','Concentration','Foco'],
cases:['我的案例','My examples','マイ事例','내 사례','Mes exemples','Meus exemplos'],
settings:['偏好设置','Preferences','設定','환경 설정','Préférences','Preferências'],
sidebarNote:['一次只做一件事。\n把注意力留给重要的事。','One thing at a time.\nMake room for what matters.','一度にひとつ。\n大切なことに集中しよう。','한 번에 하나씩.\n중요한 일에 집중하세요.','Une chose à la fois.\nPlace à l’essentiel.','Uma coisa de cada vez.\nEspaço para o que importa.'],
demoNote:['交互演示 · 不会截屏或调用 AI','Interactive demo · No screenshots or AI calls','操作デモ · 撮影・AI通信なし','체험 데모 · 화면 캡처 및 AI 호출 없음','Démo · Aucune capture ni requête IA','Demo · Sem capturas ou chamadas de IA'],
headline:['给眼前的事，一点专注。','A little space to focus.','目の前のことに、集中を。','지금 하는 일에 집중하세요.','Un espace pour se concentrer.','Um espaço para se concentrar.'],
intro:['选一件想完成的事，剩下的交给这一刻。','Choose one thing to work on. Start with this moment.','取り組むことをひとつ決めて、今ここから。','할 일을 하나 정하고, 지금 시작하세요.','Choisissez une tâche. Commencez maintenant.','Escolha uma tarefa. Comece agora.'],
sessionOnly:['仅在专注期间监督','Only monitors during a session','セッション中のみ見守ります','집중 시간에만 확인','Suivi pendant la session uniquement','Monitoramento apenas durante a sessão'],
currentSession:['当前专注','CURRENT SESSION','今回の集中','현재 집중','SESSION EN COURS','SESSÃO ATUAL'],
taskLabel:['现在想完成什么？','What would you like to work on?','今、何に取り組みますか？','지금 무엇을 하고 싶나요?','Sur quoi souhaitez-vous travailler ?','No que você quer trabalhar?'],
sampleTask:['完成产品方案初稿','Draft the product proposal','企画書の初稿を仕上げる','제품 제안서 초안 작성','Rédiger la proposition produit','Escrever a proposta do produto'],
min:['分钟','min','分','분','min','min'],
screenNotice:['监督期间定时截屏，由所选 AI 服务判断是否专注。','During a session, screenshots are sent to your chosen AI service.','セッション中は画面を撮影し、選択したAIサービスに送信します。','집중 중 화면을 캡처하여 선택한 AI 서비스로 전송합니다.','Pendant la session, des captures sont envoyées au service IA choisi.','Durante a sessão, capturas são enviadas ao serviço de IA escolhido.'],
liveStatus:['实时状态','LIVE STATUS','リアルタイム状況','실시간 상태','ÉTAT EN DIRECT','STATUS AO VIVO'],
nextCheck:['下次检查','Next check','次の確認','다음 확인','Prochaine vérification','Próxima verificação'],
reference:['本次参考案例','Examples referenced','参照した事例','참고한 사례','Exemples consultés','Exemplos consultados'],
referenceHint:['你的反馈会成为参考，帮助 AI 理解哪些活动与任务有关。','Your feedback helps the AI understand which activities relate to your task.','フィードバックは、タスクに関係する活動をAIが理解する手がかりになります。','피드백은 AI가 작업과 관련된 활동을 이해하는 데 도움이 됩니다.','Vos retours aident l’IA à comprendre les activités liées à votre tâche.','Seu feedback ajuda a IA a entender quais atividades se relacionam à tarefa.'],
recent:['最近判定','Recent checks','最近の判定','최근 판단','Vérifications récentes','Verificações recentes'],
sampleRecords:['示例记录 · 点击纠正可体验','Sample records · Try correcting a check','サンプル記録 · 修正をお試しください','예시 기록 · 판단 수정 체험','Exemples · Essayez de corriger un avis','Exemplos · Experimente corrigir uma avaliação'],
tryStates:['体验其他状态','Explore other states','他の状態を体験','다른 상태 체험','Explorer d’autres états','Explorar outros estados'],
previewBlock:['预览分心拦截 ↗','Preview interruption ↗','中断画面を表示 ↗','차단 화면 미리보기 ↗','Voir l’interruption ↗','Ver interrupção ↗'],
previewError:['模拟 AI 连接失败','Simulate AI connection error','AI接続エラーを試す','AI 연결 오류 체험','Simuler une erreur IA','Simular erro de conexão IA'],
casesIntro:['让 AI 更理解你的工作方式。','Help the AI understand how you work.','あなたの働き方を、AIに伝えよう。','AI가 나의 작업 방식을 이해하도록 도와주세요.','Aidez l’IA à comprendre votre façon de travailler.','Ajude a IA a entender como você trabalha.'],
caseInfo:['相似任务中，AI 会参考你保存的判断和原因。这些是参考案例，不是永久白名单。','The AI can reference your feedback in similar tasks. Examples are guidance, not permanent exceptions.','似たタスクで保存した判断と理由を参照します。事例は参考であり、永続的な例外ではありません。','유사한 작업에서 저장한 판단과 이유를 참고합니다. 사례가 영구 허용을 의미하지는 않습니다.','L’IA peut consulter vos retours pour des tâches similaires. Ce sont des repères, pas des exceptions permanentes.','A IA pode consultar seu feedback em tarefas semelhantes. São referências, não exceções permanentes.'],
settingsIntro:['用你习惯的语言，找回自己的节奏。','Your language. Your rhythm.','使い慣れた言葉で、自分のペースを。','익숙한 언어로 나만의 리듬을 찾으세요.','Votre langue. Votre rythme.','Seu idioma. Seu ritmo.'],
languages:['语言','Languages','言語','언어','Langues','Idiomas'],
uiLanguage:['界面语言','Interface language','表示言語','화면 언어','Langue de l’interface','Idioma da interface'],
uiHint:['用于导航、状态和提示。','Navigation, status and messages.','ナビゲーション、状況、メッセージの言語。','탐색, 상태 및 안내에 사용됩니다.','Navigation, états et messages.','Navegação, status e mensagens.'],
answerLanguage:['答题语言','Question language','問題の言語','문제 언어','Langue des questions','Idioma das perguntas'],
answerHint:['题目和选项使用此语言，与界面语言独立。','Questions and choices use this language, independently of the interface.','問題と選択肢に使用します。表示言語とは別に設定できます。','화면 언어와 별개로 문제와 선택지에 사용됩니다.','Langue des questions et des choix, indépendante de l’interface.','Idioma das perguntas e opções, independente da interface.'],
questionPreview:['题目预览','QUESTION PREVIEW','問題プレビュー','문제 미리보기','APERÇU DE QUESTION','PRÉVIA DA PERGUNTA'],
advanced:['监督细节','Monitoring details','見守りの詳細','집중 확인 설정','Détails du suivi','Detalhes do monitoramento'],
interval:['检查间隔','Check interval','確認間隔','확인 간격','Intervalle de vérification','Intervalo de verificação'],
threshold:['连续分心几次后拦截','Consecutive distractions before interruption','中断までの連続脱線回数','차단 전 연속 이탈 횟수','Distractions consécutives avant interruption','Distrações consecutivas antes de interromper'],
autoSaved:['设置自动保存在当前浏览器。','Preferences are saved in this browser.','設定はこのブラウザに保存されます。','설정은 현재 브라우저에 저장됩니다.','Les préférences sont enregistrées dans ce navigateur.','As preferências são salvas neste navegador.'],
footer:['专注监督 · 个人案例','Focus monitoring · Personal examples','集中の見守り · 個人の事例','집중 확인 · 개인 사례','Suivi de concentration · Exemples personnels','Monitoramento de foco · Exemplos pessoais'],
exitPreview:['退出演示 ✕','Exit preview ✕','デモを閉じる ✕','미리보기 종료 ✕','Quitter la démo ✕','Sair da demo ✕'],
blockTitle:['先停一下，\n把注意力带回来。','Pause a moment.\nCome back to your task.','ひと息おいて、\nタスクに戻ろう。','잠시 멈추고,\n다시 집중하세요.','Un instant de pause.\nRevenez à votre tâche.','Faça uma pausa.\nVolte à sua tarefa.'],
blockIntro:['你似乎偏离了当前任务。完成一道小题，再继续。','You seem to have drifted from your task. Answer a short question to continue.','タスクから離れているようです。短い問題に答えて、再開しましょう。','현재 작업에서 벗어난 것 같아요. 간단한 문제를 풀고 계속하세요.','Vous semblez vous être éloigné de votre tâche. Répondez à une question pour reprendre.','Você parece ter se afastado da tarefa. Responda a uma pergunta para continuar.'],
yourTask:['你的任务','YOUR TASK','あなたのタスク','내 작업','VOTRE TÂCHE','SUA TAREFA'],
noticed:['AI 注意到','AI NOTICED','AIが検出したこと','AI가 감지한 내용','OBSERVATION DE L’IA','OBSERVAÇÃO DA IA'],
offReason:['正在观看视频，暂未识别出与产品方案的关联。','A video is playing; its connection to the product proposal is unclear.','動画を視聴中ですが、企画書との関連はまだ確認できません。','동영상을 시청 중이며 제품 제안서와의 관련성이 불분명합니다.','Une vidéo est en cours ; son lien avec la proposition produit reste incertain.','Um vídeo está sendo reproduzido; a relação com a proposta ainda não está clara.'],
actuallyWorking:['其实我在做任务 → 纠正判断','I’m working on my task → Correct this','タスクに取り組んでいます → 判定を修正','작업 중이에요 → 판단 수정','Je travaille sur ma tâche → Corriger','Estou trabalhando na tarefa → Corrigir'],
smallQuestion:['一道小题，重新出发','A SMALL RESET','小さな問題で、再スタート','간단한 문제로 다시 시작','UNE PETITE PAUSE ACTIVE','UM PEQUENO RECOMEÇO'],
checkAnswer:['确认答案','Check answer','答えを確認','정답 확인','Vérifier la réponse','Verificar resposta'],
returnToWork:['回到任务 →','Return to task →','タスクに戻る →','작업으로 돌아가기 →','Reprendre la tâche →','Voltar à tarefa →'],
quizNote:['演示题目 · 答对后即可返回当前任务','Demo question · Answer correctly to return to your task','デモ問題 · 正解するとタスクに戻れます','예시 문제 · 정답을 맞히면 작업으로 돌아갑니다','Question de démo · Répondez juste pour reprendre','Pergunta de demo · Acerte para voltar à tarefa'],
correctTitle:['帮 AI 理解这一次','Help the AI understand','今回の状況をAIに伝える','AI가 상황을 이해하도록 도와주세요','Aidez l’IA à comprendre','Ajude a IA a entender'],
correctIntro:['结合截图和当前任务，告诉我们实际情况。','Use the screen and task context to explain what was happening.','画面とタスクをもとに、実際の状況を教えてください。','화면과 현재 작업을 바탕으로 실제 상황을 알려주세요.','Expliquez la situation en vous appuyant sur l’écran et la tâche.','Explique a situação com base na tela e na tarefa.'],
illustration:['示意画面 · 非真实截屏','Illustration · Not a real capture','イメージ · 実際の画面ではありません','예시 화면 · 실제 캡처 아님','Illustration · Pas une capture réelle','Ilustração · Não é uma captura real'],
videoTitle:['产品设计案例解析','Product design walkthrough','プロダクトデザイン解説','제품 디자인 사례 분석','Analyse de conception produit','Análise de design de produto'],
videoDescription:['设计研究 / 视频参考','Design research / Video reference','デザイン調査 / 参考動画','디자인 조사 / 참고 영상','Recherche design / Vidéo de référence','Pesquisa de design / Vídeo de referência'],
aiJudgment:['AI 当时的判断','Original AI judgment','AIの元の判断','당시 AI 판단','Avis initial de l’IA','Avaliação original da IA'],
actualLabel:['实际上，我在…','I was actually…','実際には…','실제로는…','En réalité, j’étais…','Na verdade, eu estava…'],
onTask:['做任务','On task','タスク中','작업 중','Sur ma tâche','Na tarefa'],
offTask:['分心','Off task','脱線中','집중 이탈','Distrait','Distraído'],
reasonLabel:['补充一点原因','Add a little context','理由を少し追加','이유를 알려주세요','Ajoutez un peu de contexte','Adicione um pouco de contexto'],
reasonPlaceholder:['例如：这个视频是产品方案需要参考的设计案例。','For example: this video is a design reference for my proposal.','例：この動画は企画書に必要なデザインの参考です。','예: 이 영상은 제안서에 필요한 디자인 참고 자료입니다.','Ex. : cette vidéo est une référence pour ma proposition.','Ex.: este vídeo é uma referência para minha proposta.'],
saveHint:['保存截图、任务和原因，供相似情境参考；可随时删除。','Save the screen, task and reason as context for similar situations. Delete anytime.','画面・タスク・理由を似た状況の参考に保存します。いつでも削除できます。','화면, 작업, 이유를 유사한 상황의 참고 자료로 저장합니다. 언제든 삭제할 수 있습니다.','Enregistrez l’écran, la tâche et le motif comme référence. Suppression possible à tout moment.','Salve a tela, a tarefa e o motivo como referência. Exclua quando quiser.'],
saveCase:['保存为个人案例','Save personal example','マイ事例に保存','개인 사례로 저장','Enregistrer cet exemple','Salvar exemplo pessoal'],
ready:['准备就绪','Ready when you are','準備完了','준비 완료','Prêt à commencer','Pronto para começar'],
readyTitle:['为专注留出时间','Make time for focus','集中する時間をつくろう','집중할 시간을 마련하세요','Faites place à la concentration','Reserve um tempo para focar'],
readyDescription:['开始后会定时检查屏幕。你始终可以查看判定理由、纠正误判。','Start a session for periodic screen checks. You can review and correct every judgment.','開始すると定期的に画面を確認します。理由の確認や誤判定の修正ができます。','시작하면 주기적으로 화면을 확인합니다. 판단 이유를 보고 오류를 수정할 수 있어요.','Démarrez pour des vérifications régulières. Vous pouvez consulter et corriger chaque avis.','Inicie para verificar a tela periodicamente. Você pode revisar e corrigir cada avaliação.'],
start:['开始专注 →','Start focusing →','集中を始める →','집중 시작 →','Commencer →','Começar →'],
stop:['结束本次专注','End session','セッションを終了','집중 종료','Terminer la session','Encerrar sessão'],
running:['专注进行中','Session active','集中セッション中','집중 진행 중','Session active','Sessão ativa'],
remaining:['剩余时间','TIME REMAINING','残り時間','남은 시간','TEMPS RESTANT','TEMPO RESTANTE'],
planned:['专注时长','FOCUS DURATION','集中時間','집중 시간','DURÉE DE CONCENTRATION','DURAÇÃO DO FOCO'],
timerHint:['留在这一件事上','One thing at a time','ひとつのことに集中','한 가지 일에 집중','Une chose à la fois','Uma coisa de cada vez'],
focusedTitle:['你正在专注','You’re on track','集中できています','잘 집중하고 있어요','Vous êtes sur la bonne voie','Você está no caminho certo'],
focusedDescription:['正在编辑产品方案，与当前任务一致。继续保持这个节奏。','You’re editing the proposal, which matches your task. Keep going.','企画書を編集中で、タスクと一致しています。この調子で。','제안서 편집은 현재 작업과 일치해요. 이 흐름을 이어가세요.','Vous modifiez la proposition, en accord avec votre tâche. Continuez ainsi.','Você está editando a proposta, de acordo com a tarefa. Continue assim.'],
correct:['纠正判断','Review judgment','判定を修正','판단 수정','Revoir l’avis','Revisar avaliação'],
docTitle:['编辑方案文档','Editing the proposal','企画書の編集','제안서 편집','Modification de la proposition','Editando a proposta'],
docReason:['当前内容与任务相关','The content relates to the task','内容はタスクに関連しています','현재 내용이 작업과 관련됨','Le contenu est lié à la tâche','O conteúdo está relacionado à tarefa'],
videoReason:['正在为产品方案收集设计参考。','Collecting design references for the product proposal.','企画書のためにデザインの参考資料を収集中。','제품 제안서의 디자인 참고 자료를 수집 중입니다.','Recherche de références design pour la proposition produit.','Coletando referências de design para a proposta do produto.'],
saved:['案例已保存，可在「我的案例」中查看。','Example saved. Find it in My examples.','保存しました。「マイ事例」で確認できます。','사례를 저장했어요. 내 사례에서 확인하세요.','Exemple enregistré dans Mes exemples.','Exemplo salvo em Meus exemplos.'],
deleted:['案例已删除','Example deleted','事例を削除しました','사례를 삭제했어요','Exemple supprimé','Exemplo excluído'],
delete:['删除','Delete','削除','삭제','Supprimer','Excluir'],
empty:['还没有案例。可以从最近判定中保存第一条反馈。','No examples yet. Save your first feedback from a recent check.','事例はまだありません。最近の判定からフィードバックを保存できます。','아직 사례가 없어요. 최근 판단에서 첫 피드백을 저장하세요.','Aucun exemple. Enregistrez un retour depuis une vérification récente.','Nenhum exemplo. Salve seu primeiro feedback em uma avaliação recente.'],
errorTitle:['AI 暂时无法连接','AI is temporarily unavailable','AIに接続できません','AI에 일시적으로 연결할 수 없어요','L’IA est temporairement indisponible','A IA está temporariamente indisponível'],
errorDescription:['本次检查未完成，不计为分心。点击重试恢复演示。','This check was not completed and is not counted as distraction. Retry to restore the demo.','確認できなかったため脱線には数えません。再試行でデモを復旧します。','확인이 완료되지 않아 집중 이탈로 계산하지 않습니다. 다시 시도해 데모를 복구하세요.','Cette vérification n’est pas comptée comme distraction. Réessayez pour rétablir la démo.','Esta verificação não conta como distração. Tente novamente para restaurar a demo.'],
retry:['重试连接','Retry connection','接続を再試行','연결 재시도','Réessayer','Tentar novamente'],
finished:['本次专注已结束。准备好时，再开始一轮。','Session finished. Start another when you’re ready.','セッションが終了しました。準備ができたら次の集中へ。','집중 시간이 끝났어요. 준비되면 다시 시작하세요.','Session terminée. Recommencez quand vous le souhaitez.','Sessão encerrada. Comece outra quando quiser.'],
pickAnswer:['请先选择一个答案。','Choose an answer first.','答えを選んでください。','먼저 답을 선택하세요.','Choisissez d’abord une réponse.','Escolha uma resposta primeiro.'],
wrong:['再想一下：先确定一个小步骤，会更容易开始。','Try again: a clear small step makes it easier to begin.','もう一度。小さな一歩を決めると始めやすくなります。','다시 생각해 보세요. 작은 단계를 정하면 시작하기 쉬워요.','Réessayez : une petite étape précise facilite le démarrage.','Tente novamente: um pequeno passo claro facilita começar.'],
right:['答对了。带着这一个小步骤，回到任务。','Correct. Take that small step back to your task.','正解です。その小さな一歩からタスクに戻りましょう。','정답이에요. 작은 단계부터 작업으로 돌아가세요.','Exact. Reprenez votre tâche avec cette petite étape.','Correto. Retome a tarefa com esse pequeno passo.'],
savedDate:['保存在此设备','Saved on this device','この端末に保存済み','이 기기에 저장됨','Enregistré sur cet appareil','Salvo neste dispositivo']
};
const quizzes = {
zh:{q:'想开始一项复杂任务，哪种做法更容易迈出第一步？',a:['同时打开多个任务。','把任务拆成一个具体的小步骤。','等到完全有动力再开始。']},
en:{q:'What makes it easier to start a complex task?',a:['Open several tasks at once.','Break it into one clear, small step.','Wait until you feel fully motivated.']},
ja:{q:'複雑なタスクに取りかかるには、どの方法がよいでしょう？',a:['複数のタスクを同時に開く。','具体的な小さな一歩に分ける。','やる気が十分に出るまで待つ。']},
ko:{q:'복잡한 작업을 시작할 때 첫걸음을 쉽게 만드는 방법은?',a:['여러 작업을 동시에 연다.','구체적이고 작은 단계 하나로 나눈다.','의욕이 충분히 생길 때까지 기다린다.']},
fr:{q:'Comment commencer plus facilement une tâche complexe ?',a:['Ouvrir plusieurs tâches à la fois.','Définir une première petite étape concrète.','Attendre d’être pleinement motivé.']},
pt:{q:'O que facilita começar uma tarefa complexa?',a:['Abrir várias tarefas ao mesmo tempo.','Dividir em um primeiro passo pequeno e concreto.','Esperar até sentir muita motivação.']}
};
const $ = id => document.getElementById(id);
const key = 'focusguard.mvp-demo.v1';
let stored = {};
try { stored = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch (_) {}
let ui = LANGS[stored.ui] ? stored.ui : 'zh';
let answer = LANGS[stored.answer] ? stored.answer : 'zh';
let examples = Array.isArray(stored.examples) ? stored.examples.filter(x => x && typeof x.id === 'string' && ['on','off'].includes(x.verdict) && typeof x.reason === 'string' && typeof x.task === 'string') : [
  {id:'seed-video',verdict:'on',reason:'',task:'',seed:'video'},
  {id:'seed-document',verdict:'on',reason:'',task:'',seed:'doc'}
];
let view='focus', running=false, seconds=25*60, duration=25, deadline=0, error=false, selected=-1, passed=false, fromBlock=false, recordType='video', nextDeadline=0;
let lastDefaultTask='';
function t(k,lang=ui){return copy[k]?.[Object.keys(LANGS).indexOf(lang)] ?? k;}
function persist(){try{localStorage.setItem(key,JSON.stringify({ui,answer,examples,interval:$('interval').value,threshold:$('threshold').value}));}catch(_){ /* file:// or private browsing may disallow storage. */ }}
function languageOptions(el,value){el.replaceChildren(...Object.entries(LANGS).map(([code,name])=>{const opt=document.createElement('option');opt.value=code;opt.textContent=name;return opt;}));el.value=value;}
function toast(k){$('toast').textContent=t(k);$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,3500);}
function changeView(name){view=name;document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!==name+'View');document.querySelectorAll('[data-view]').forEach(el=>el.classList.toggle('active',el.dataset.view===name));$('crumb').textContent=t(name);}
function render(){
  document.documentElement.lang={zh:'zh-CN',en:'en',ja:'ja',ko:'ko',fr:'fr',pt:'pt'}[ui];
  document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n));
  if(!$('task').value || $('task').value===lastDefaultTask) $('task').value=t('sampleTask');
  lastDefaultTask=t('sampleTask');
  ['uiLanguage','settingsUi'].forEach(id=>languageOptions($(id),ui));
  ['answerLanguage','quizLanguage'].forEach(id=>languageOptions($(id),answer));
  $('correctionReason').placeholder=t('reasonPlaceholder');
  $('questionPreview').textContent=quizzes[answer].q;
  changeView(view);renderStatus();renderRecords();renderCases();renderQuiz();
  $('originalJudgment').textContent=t(recordType==='video'?'offTask':'onTask');
}
function formatTime(n){return `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;}
function renderStatus(){
  $('sessionBadge').textContent=t(running?'running':'ready');
  $('sessionAction').textContent=t(running?'stop':'start');
  $('task').disabled=running;
  $('timerCaption').textContent=t(running?'remaining':'planned');
  $('timerFoot').textContent=t('timerHint');
  $('timer').textContent=formatTime(seconds);
  $('ringProgress').style.strokeDashoffset=703.72*(1-seconds/(duration*60));
  document.querySelectorAll('[data-minutes]').forEach(b=>{b.disabled=running;b.classList.toggle('selected',Number(b.dataset.minutes)===duration);});
  $('statusTitle').textContent=t(error?'errorTitle':running?'focusedTitle':'readyTitle');
  $('statusDescription').textContent=t(error?'errorDescription':running?'focusedDescription':'readyDescription');
  $('statusIcon').textContent=error?'!':running?'✓':'◎';
  $('statusIcon').style.background=error?'#fff1df':'#edf7f2';
  $('statusIcon').style.color=error?'#ae6b1a':'#24896f';
  $('referenceCount').textContent=running&&!error?String(Math.min(1,examples.length)):'—';
  $('nextCheck').textContent=running&&!error?formatTime(Math.max(0,Math.ceil((nextDeadline-Date.now())/1000))):'—';
  $('previewError').textContent=t(error?'retry':'previewError');
}
const records=[{type:'doc',time:'14:32',title:'docTitle',reason:'docReason',verdict:'on'},{type:'video',time:'14:27',title:'videoTitle',reason:'offReason',verdict:'off'}];
function renderRecords(){
  $('records').replaceChildren(...records.map(rec=>{
    const row=document.createElement('div');row.className='record';
    const symbol=document.createElement('span');symbol.className='record-symbol';symbol.textContent=rec.type==='doc'?'▤':'▷';
    const content=document.createElement('div');content.className='record-content';
    const title=document.createElement('div');title.className='record-title';title.textContent=t(rec.title);
    const detail=document.createElement('div');detail.className='record-detail';detail.textContent=t(rec.reason);
    content.append(title,detail);
    const time=document.createElement('time');time.textContent=rec.time;
    const pill=document.createElement('span');pill.className='pill'+(rec.verdict==='off'?' warning':'');pill.textContent=t(rec.verdict==='off'?'offTask':'onTask');
    const button=document.createElement('button');button.className='text-button';button.textContent=t('correct')+' ↗';button.onclick=()=>openCorrection(rec.type,false);
    row.append(symbol,content,time,pill,button);return row;
  }));
}
function renderCases(){
  $('caseCount').textContent=examples.length;$('caseTotal').textContent=String(examples.length);
  const container=$('caseList');container.replaceChildren();
  if(!examples.length){const empty=document.createElement('p');empty.className='empty';empty.textContent=t('empty');container.append(empty);return;}
  examples.forEach(ex=>{
    const card=document.createElement('article');card.className='case-card';
    const preview=document.querySelector('#correctionDialog .screen-preview').cloneNode(true);
    preview.querySelector('strong').textContent=t(ex.seed==='doc'?'docTitle':'videoTitle');preview.querySelector('.screen-body>span').textContent=ex.seed==='doc'?'▤':'▶';preview.querySelector('.screen-body p').textContent=t(ex.seed==='doc'?'docReason':'videoDescription');
    const body=document.createElement('div');body.className='case-card-body';
    const badge=document.createElement('span');badge.className='pill'+(ex.verdict==='off'?' warning':'');badge.textContent=t(ex.verdict==='on'?'onTask':'offTask');
    const title=document.createElement('h2');title.textContent=ex.task||t('sampleTask');
    const reason=document.createElement('p');reason.textContent=ex.reason||t(ex.seed==='doc'?'docReason':'videoReason');
    const foot=document.createElement('div');foot.className='case-footer';
    const date=document.createElement('span');date.textContent=t('savedDate');
    const remove=document.createElement('button');remove.className='text-button delete-case';remove.textContent=t('delete');remove.onclick=()=>{examples=examples.filter(x=>x.id!==ex.id);persist();renderCases();renderStatus();toast('deleted');};
    foot.append(date,remove);body.append(badge,title,reason,foot);card.append(preview,body);container.append(card);
  });
}
function openCorrection(type,block){
  recordType=type;fromBlock=block;
  $('correctionForm').reset();$('originalJudgment').textContent=t(type==='video'?'offTask':'onTask');
  const screen=$('correctionDialog').querySelector('.screen-body');
  screen.querySelector('strong').textContent=t(type==='video'?'videoTitle':'docTitle');
  screen.querySelector('p').textContent=t(type==='video'?'videoDescription':'docReason');
  screen.querySelector('span').textContent=type==='video'?'▶':'▤';
  $('correctionDialog').showModal();
}
function renderQuiz(){
  const q=quizzes[answer];$('quizQuestion').textContent=q.q;
  $('quizOptions').replaceChildren(...q.a.map((a,i)=>{const button=document.createElement('button');button.className='quiz-option'+(selected===i?' selected':'');button.setAttribute('aria-pressed',String(selected===i));button.disabled=passed;const badge=document.createElement('b');badge.textContent=String.fromCharCode(65+i);const label=document.createElement('span');label.textContent=a;button.append(badge,label);button.onclick=()=>{selected=i;$('quizFeedback').textContent='';renderQuiz();};return button;}));
  $('quizQuestion').lang=answer;$('quizOptions').lang=answer;
  $('quizSubmit').hidden=passed;$('returnToWork').hidden=!passed;
  $('quizFeedback').textContent=passed?t('right'):'';
}
function endSession(){running=false;seconds=duration*60;error=false;renderStatus();toast('finished');}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>changeView(b.dataset.view));
document.querySelector('.brand[href]').onclick=e=>{e.preventDefault();changeView('focus');};
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
['uiLanguage','settingsUi'].forEach(id=>$(id).onchange=e=>{ui=e.target.value;persist();render();});
['answerLanguage','quizLanguage'].forEach(id=>$(id).onchange=e=>{answer=e.target.value;selected=-1;passed=false;persist();render();});
document.querySelectorAll('[data-minutes]').forEach(b=>b.onclick=()=>{if(running)return;duration=Number(b.dataset.minutes);seconds=duration*60;renderStatus();});
if(['60','180','300'].includes(stored.interval))$('interval').value=stored.interval;
if(['1','2','3'].includes(stored.threshold))$('threshold').value=stored.threshold;
['interval','threshold'].forEach(id=>$(id).onchange=()=>{persist();nextDeadline=Date.now()+Number($('interval').value)*1000;renderStatus();});
$('sessionAction').onclick=()=>{if(running){endSession();return;}if(!$('task').value.trim()){$('task').value='';$('task').reportValidity();return;}running=true;error=false;deadline=Date.now()+seconds*1000;nextDeadline=Date.now()+Number($('interval').value)*1000;renderStatus();};
$('previewError').onclick=()=>{error=!error;renderStatus();};
$('previewBlock').onclick=()=>{selected=-1;passed=false;renderQuiz();$('blockedTask').textContent=$('task').value;$('blockDialog').showModal();};
$('blockCorrection').onclick=()=>openCorrection('video',true);
$('quizSubmit').onclick=()=>{if(selected<0){$('quizFeedback').textContent=t('pickAnswer');return;}if(selected!==1){$('quizFeedback').textContent=t('wrong');return;}passed=true;renderQuiz();$('returnToWork').focus();};
$('returnToWork').onclick=()=>{$('blockDialog').close();};
$('correctionForm').onsubmit=e=>{e.preventDefault();const reason=$('correctionReason').value.trim();if(!reason){$('correctionReason').value='';$('correctionReason').reportValidity();return;}examples.unshift({id:'case-'+Date.now(),verdict:new FormData(e.target).get('verdict'),task:$('task').value.trim()||t('sampleTask'),reason,seed:recordType});persist();renderCases();renderStatus();$('correctionDialog').close();if(fromBlock && $('blockDialog').open)$('blockDialog').close();toast('saved');};
// Wall-clock countdown. Demo dialogs freeze the session, as a real blocker would.
let lastTick=Date.now();
setInterval(()=>{const now=Date.now(),elapsed=now-lastTick;lastTick=now;if(!running)return;if($('blockDialog').open||$('correctionDialog').open){deadline+=elapsed;nextDeadline+=elapsed;return;}seconds=Math.max(0,Math.ceil((deadline-now)/1000));if(now>=nextDeadline)nextDeadline=now+Number($('interval').value)*1000;if(seconds===0){endSession();return;}renderStatus();},250);
render();
