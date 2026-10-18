import type * as React from 'react';
import type { ChatDisplayBindings } from './ChatView';

/** Only presentation: the persistent ChatPane owns state, streams and callbacks. */
export function renderChatDisplay(bindings: ChatDisplayBindings) {
  const { ActionGrimoire, BookOpen, Bot, CameraPreview, ChatInputArea, ConversationActions, Fragment, History, HistoryDate, Loader2, MessageBubble, PlanModePanel, QuestionPanel, ReactMarkdown, RefreshCw, RotateCw, SystemAIChatHistoryDialog, TodoPanel, ToolHistoryPanel, X, active, agentLabel, conversationLabel, currentToolLabel, datedHistory, dialogRef, fileAttachments, followRef, grimoireOpen, handleApprovePlan, handleCancel, handleClear, handleDragStart, handleKeyDown, handleRejectPlan, handleResetSession, handleResizeStart, handleSubmitAnswer, headerActions, headerItems, historyDay, input, inputRef, isAgent, isDialog, isDragging, isLoading, isResizing, messages, messagesEndRef, messagesScrollRef, onClose, planMode, position, questionStatus, questions, readingOlder, remarkGfm, resizeDirection, selectedAction, sendMessage, session, setGrimoireOpen, setInput, setReadingOlder, setSelectedAction, setShowHistory, show, showHistory, showResetSessionButton, size, streamingContent, thinkingText, todos, toolHistory, variant } = bindings;
  // ── 렌더링: 다이얼로그 모드 가시성 체크 ──

  if (isDialog && !show) return null;

  // ── 공통 채팅 내부 UI ──

  const chatContent = (
    <>
      {/* 헤더 (다이얼로그 모드에서는 드래그 핸들) */}
      <div
        className={'chat-header ' + (isDialog
          ? 'h-10 flex items-center justify-between gap-2 min-w-0 px-2 border-b border-gray-200 bg-gradient-to-r from-amber-50 to-orange-50 shrink-0 select-none'
          : 'h-10 px-2 flex items-center justify-between gap-2 min-w-0 border-b border-[#E5DFD5] bg-[#EAE4DA] shrink-0 drag'
        )}
        style={isDialog ? { cursor: isDragging ? 'grabbing' : 'grab' } : undefined}
        onMouseDown={isDialog ? handleDragStart : undefined}
      >
        <div className={`flex items-center gap-2 min-w-0 flex-1${isDialog ? '' : ' no-drag'}`}>
          <div className={`w-8 h-8 shrink-0 rounded-full hidden sm:flex items-center justify-center text-white ${
            isDialog ? 'bg-gradient-to-br from-amber-400 to-orange-500' : 'bg-gradient-to-br from-[#D97706] to-[#B45309]'
          }`}>
            <Bot size={18} />
          </div>
          <div className="min-w-0">
            <div title={session?.title || agentLabel} className={isDialog ? 'truncate font-bold text-gray-800' : 'truncate font-medium text-[#4A4035]'}>
              {session?.title || agentLabel}
            </div>
          </div>
        </div>
        <div aria-label="대화 세션 메뉴" className={`flex items-center gap-1 shrink-0 whitespace-nowrap${isDialog ? '' : ' no-drag'}`}>
          <ConversationActions items={{ ...headerItems, older: (session?.hasOlder && <button disabled={readingOlder} onClick={async () => {
            if (readingOlder) return;
            setReadingOlder(true);
            const el = messagesScrollRef.current;
            const height = el?.scrollHeight || 0;
            const top = el?.scrollTop || 0;
            followRef.current = false;
            try { await session.loadOlder(); }
            finally { setReadingOlder(false); requestAnimationFrame(() => { if (el) el.scrollTop = top + el.scrollHeight - height; }); }
          }} className={`px-2 py-1.5 text-xs rounded-lg transition-colors disabled:opacity-50 ${isDialog ? 'hover:bg-amber-50 text-amber-600' : 'hover:bg-[#FFE9B8] text-[#92400E]'}`}>{readingOlder ? '불러오는 중…' : conversationLabel('older')}</button>), dictionary: headerItems?.dictionary !== undefined ? headerItems.dictionary : (<button
            onClick={() => setGrimoireOpen(true)}
            className={`flex items-center gap-1 px-2 py-1.5 text-xs rounded-lg transition-colors ${isDialog ? 'hover:bg-amber-50 text-amber-600' : 'hover:bg-[#FFE9B8] text-[#92400E]'}`}
            title="마법책 — IBL 액션 사전" aria-label="IBL 사전"
          >
            <BookOpen size={14} className="hidden sm:block" />{conversationLabel('dictionary')}
          </button>) }} />
          {headerActions}
          {/* Claude Code 세션 재시작 (Claude Code provider일 때만) */}
          {showResetSessionButton && (
            <button onClick={handleResetSession} className={`p-1.5 rounded-lg transition-colors ${isDialog ? 'hover:bg-gray-200' : 'hover:bg-[#DDD5C8]'}`} title="Claude Code 새 세션 시작 (누적 컨텍스트 끊기)">
              <RotateCw size={16} className={isDialog ? 'text-gray-500' : 'text-[#6B5B4F]'} />
            </button>
          )}
          {/* 히스토리/초기화 (시스템 AI일 때) */}
          {!isAgent && !session && (
            <>
              <button onClick={() => setShowHistory(true)} className={`p-1.5 rounded-lg transition-colors ${isDialog ? 'hover:bg-gray-200' : 'hover:bg-[#DDD5C8]'}`} title="대화 히스토리">
                <History size={16} className={isDialog ? 'text-gray-500' : 'text-[#6B5B4F]'} />
              </button>
              <button onClick={handleClear} className={`p-1.5 rounded-lg transition-colors ${isDialog ? 'hover:bg-gray-200' : 'hover:bg-[#DDD5C8]'}`} title="대화 초기화">
                <RefreshCw size={16} className={isDialog ? 'text-gray-500' : 'text-[#6B5B4F]'} />
              </button>
            </>
          )}
          {/* 닫기 버튼 (다이얼로그 전용) */}
          {isDialog && onClose && (
            <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors">
              <X size={20} className="text-gray-500" />
            </button>
          )}
        </div>
      </div>

      {session?.error && <p role="alert" className="px-4 py-2 text-sm text-red-600">{session.error}</p>}

      {/* TODO 패널 (로딩 아닐 때, 다이얼로그 모드) */}
      {!isLoading && isDialog && <TodoPanel todos={todos} variant="neutral" collapsible />}

      {/* 질문 패널 */}
      {questionStatus === 'pending' && questions.length > 0 && (
        <QuestionPanel questions={questions} onSubmit={handleSubmitAnswer} />
      )}

      {/* 계획 모드 패널 */}
      <PlanModePanel planMode={planMode} onApprove={handleApprovePlan} onReject={handleRejectPlan} />

      {/* 메시지+입력 래퍼 — flex-1 min-h-0으로 남은 공간 전부 차지, 내부에서 메시지 스크롤.
          relative: 히스토리 판이 이 안(헤더 아래)에만 덮이게 하는 좌표계 — 헤더를 덮으면 창 이동이 죽는다. */}
      <div className="relative flex-1 min-h-0 flex flex-col overflow-hidden">

      {/* 메시지 영역 */}
      <div ref={messagesScrollRef} onScroll={e => { const el = e.currentTarget; followRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; }} className={`flex-1 min-h-0 overflow-y-auto p-4 space-y-4 ${isDialog ? 'bg-gray-50 selectable-text dialog-messages-scroll' : ''}`}>

        {messages.length === 0 && !isLoading ? (
          <div className={`h-full flex items-center justify-center ${isDialog ? 'text-gray-400' : 'text-[#A09080]'}`}>
            <div className="text-center">
              <Bot size={48} className="mx-auto mb-3 opacity-50" />
              <p className={isDialog ? 'text-sm' : ''}>{isDialog ? '무엇을 도와드릴까요?' : `${agentLabel}에게 메시지를 보내보세요`}</p>
              {isDialog && <p className="text-xs mt-1">시스템 설정, 에이전트 관리 등을 도와드립니다</p>}
            </div>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <Fragment key={msg.id || idx}>
              {datedHistory && (idx === 0 || historyDay(messages[idx - 1].timestamp) !== historyDay(msg.timestamp)) &&
                <div data-message-day={historyDay(msg.timestamp)} className="flex items-center gap-3 py-2 text-xs text-[#8B7355]"><span className="h-px flex-1 bg-[#D8D0C5]"/><HistoryDate day={historyDay(msg.timestamp)}/><span className="h-px flex-1 bg-[#D8D0C5]"/></div>}
              <MessageBubble message={msg} variant={variant} />
            </Fragment>
          ))
        )}

        {/* 스트리밍 중인 응답 */}
        {isLoading && (
          isDialog ? (
            // 다이얼로그 모드: 버블 안에 모든 것
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm max-w-[80%] min-w-0 break-words">
                <TodoPanel todos={todos} variant="inline" />
                <ToolHistoryPanel toolHistory={toolHistory} variant="neutral" />
                {currentToolLabel && (
                  <div className="flex items-center gap-2 text-amber-600 text-sm mb-2">
                    {currentToolLabel.startsWith('✓') ? <span className="text-green-500">✓</span> : <Loader2 size={14} className="animate-spin" />}
                    <span>{currentToolLabel.replace(/^[✓🔧⏳]\s*/, '')}</span>
                  </div>
                )}
                {thinkingText && (
                  <div className="flex items-center gap-2 text-gray-500 text-sm italic mb-2">
                    <Loader2 size={14} className="animate-spin" />
                    <span>{thinkingText}</span>
                  </div>
                )}
                {streamingContent ? (
                  <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2 selectable-text">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingContent}</ReactMarkdown>
                    <span className="inline-block w-2 h-4 bg-amber-400 animate-pulse ml-0.5" />
                  </div>
                ) : !currentToolLabel && !thinkingText && (
                  <div className="flex gap-1">
                    <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                )}
              </div>
            </div>
          ) : (
            // 풀페이지 모드: 독립적 블록
            <div className="space-y-2">
              <TodoPanel todos={todos} variant="inline" />
              <ToolHistoryPanel toolHistory={toolHistory} variant="warm" />
              {thinkingText && (
                <div className="flex items-center gap-2 text-[#A09080] text-sm italic">
                  <Loader2 size={14} className="animate-spin" />
                  <span>{thinkingText}</span>
                </div>
              )}
              {streamingContent && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#D97706] to-[#B45309] flex items-center justify-center flex-shrink-0 text-white">
                    <Bot size={16} />
                  </div>
                  <div className="max-w-[70%] min-w-0 break-words px-4 py-3 rounded-2xl bg-[#E5DFD5] text-[#4A4035] rounded-tl-sm">
                    <div className="chat-markdown">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingContent}</ReactMarkdown>
                    </div>
                    <span className="inline-block w-2 h-4 bg-[#D97706] animate-pulse ml-1" />
                  </div>
                </div>
              )}
              {!streamingContent && toolHistory.length === 0 && !thinkingText && (
                <div className="flex items-center gap-2 text-[#A09080]">
                  <Loader2 size={16} className="animate-spin" />
                  <span>{agentLabel}이(가) 응답 중...</span>
                </div>
              )}
            </div>
          )
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 입력 영역 */}
      <ChatInputArea
        input={input}
        onInputChange={setInput}
        onSend={sendMessage}
        onCancel={handleCancel}
        onKeyDown={handleKeyDown}
        isLoading={isLoading}
        allowSteering={!session || session.canSteer}
        hasContent={!!input.trim() || fileAttachments.hasAttachments}
        attachedImages={fileAttachments.attachedImages}
        attachedTextFiles={fileAttachments.attachedTextFiles}
        attachedDocuments={fileAttachments.attachedDocuments}
        isDragging={fileAttachments.isDragging}
        onDragOver={fileAttachments.handleDragOver}
        onDragLeave={fileAttachments.handleDragLeave}
        onDrop={fileAttachments.handleDrop}
        onPaste={fileAttachments.handlePaste}
        onFileSelect={fileAttachments.handleFileSelect}
        onRemoveImage={fileAttachments.removeImage}
        onRemoveTextFile={fileAttachments.removeTextFile}
        onRemoveDocument={fileAttachments.removeDocument}
        onCameraClick={() => fileAttachments.setIsCameraOpen(true)}
        selectedAction={selectedAction}
        onClearAction={() => setSelectedAction(null)}
        fileInputRef={fileAttachments.fileInputRef}
        inputRef={inputRef}
        placeholder={isAgent ? `${agentLabel}에게 메시지 보내기... (파일 드래그/붙여넣기 가능)` : '메시지를 입력하세요... (파일 드래그/붙여넣기 가능)'}
        variant={variant}
        showHelpText={isDialog}
      />

      {/* 히스토리 (시스템 AI) — 창 안에 갇힌 판. 헤더(창 이동 손잡이)는 늘 드러나 있다. */}
      {!isAgent && !session && (
        <SystemAIChatHistoryDialog show={showHistory} onClose={() => setShowHistory(false)} />
      )}

      </div>{/* 메시지+입력 래퍼 닫기 */}

      {/* 마법책 (IBL 액션 사전) 모달 */}
      <ActionGrimoire
        open={grimoireOpen}
        onClose={() => setGrimoireOpen(false)}
        onSelect={(actionId) => {
          // 같은 액션을 다시 누르면 해제, 아니면 선택
          setSelectedAction((prev) => (prev === actionId ? null : actionId));
        }}
      />

      {/* 카메라 */}
      <CameraPreview
        isOpen={active && fileAttachments.isCameraOpen}
        onClose={() => fileAttachments.setIsCameraOpen(false)}
        onCapture={fileAttachments.handleCameraCapture}
      />
    </>
  );

  // ── 레이아웃 래핑 ──

  if (isDialog) {
    const dialogStyle: React.CSSProperties = {
      width: `min(${size.width}px, 95vw)`,
      height: `min(${size.height}px, 95vh)`,
      cursor: isResizing ? (resizeDirection.includes('n') || resizeDirection.includes('s') ? 'ns-resize' : resizeDirection.includes('e') || resizeDirection.includes('w') ? 'ew-resize' : 'nwse-resize') : 'default',
      ...(position ? { position: 'absolute' as const, left: position.x, top: position.y } : {})
    };

    return (
      <div
        className={`fixed inset-0 z-50 ${position ? '' : 'flex items-center justify-center'}`}
        style={{ backgroundColor: isDragging || isResizing ? 'transparent' : 'rgba(0,0,0,0.3)' }}
        onClick={(e) => { if (e.target === e.currentTarget && onClose) onClose(); }}
      >
        <div
          ref={dialogRef}
          className="chat-dialog bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden relative"
          style={dialogStyle}
        >
          {/* 리사이즈 핸들 */}
          <div className="absolute top-0 left-4 right-4 h-1 cursor-ns-resize hover:bg-amber-400/50 z-10" onMouseDown={(e) => handleResizeStart(e, 'n')} />
          <div className="absolute bottom-0 left-4 right-4 h-1 cursor-ns-resize hover:bg-amber-400/50 z-10" onMouseDown={(e) => handleResizeStart(e, 's')} />
          <div className="absolute left-0 top-4 bottom-4 w-1 cursor-ew-resize hover:bg-amber-400/50 z-10" onMouseDown={(e) => handleResizeStart(e, 'w')} />
          <div className="absolute right-0 top-4 bottom-4 w-1 cursor-ew-resize hover:bg-amber-400/50 z-10" onMouseDown={(e) => handleResizeStart(e, 'e')} />
          <div className="absolute top-0 left-0 w-4 h-4 cursor-nwse-resize z-20" onMouseDown={(e) => handleResizeStart(e, 'nw')} />
          <div className="absolute top-0 right-0 w-4 h-4 cursor-nesw-resize z-20" onMouseDown={(e) => handleResizeStart(e, 'ne')} />
          <div className="absolute bottom-0 left-0 w-4 h-4 cursor-nesw-resize z-20" onMouseDown={(e) => handleResizeStart(e, 'sw')} />
          <div className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize z-20" onMouseDown={(e) => handleResizeStart(e, 'se')} />

          {chatContent}
        </div>
      </div>
    );
  }

  // 풀페이지 모드
  // min-w-0: flex-row 부모(Manager 메인영역) 안에서 이 열이 내용 고유폭 아래로 줄어들 수 있게 한다.
  // 없으면 창 축소 시 열이 넓은 채로 남아 max-w-[70%] 버블이 부모 overflow-hidden에 잘린다.
  return (
    <div className="flex-1 min-w-0 min-h-0 flex flex-col bg-[#F5F1EB]">
      {chatContent}
    </div>
  );
}
