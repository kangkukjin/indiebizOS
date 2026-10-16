import type { LauncherDisplayBindings } from './Launcher';
export function renderLauncherDisplay(bindings: LauncherDisplayBindings) {
  const { ActionDesktop, ActiveModeIcon, BACKEND_ORIGIN, BookOpen, Bot, Boxes, ChevronDown, Clock, Contact, ContextMenu, DraggableIcon, DraggableTrash, FileText, Folder, ForageBrowser, Globe, GuideDialog, HelpCircle, IS_WEB_SURFACE, Info, LAUNCHER_MODES, LanguagePicker, Laptop, Layers, MODE_META, ManualMode, NewFolderDialog, NewProjectDialog, OnboardingDialog, ScanLine, SchedulerDialog, Settings, SettingsDialog, Smartphone, SwitchEditDialog, TrashDialog, UiText, UserManualDialog, Users, WarehouseView, X, Zap, activeAppId, activeMeta, alert, api, appOpenNonce, browserOpen, checkFolderHover, checkTrashHover, clipToPhone, clipboard, closeContextMenu, console, contextMenu, demotePromoted, desktopRef, displayProjects, displaySwitches, editingSwitchData, error, folderRefs, formatLastRun, getItemName, handleArrangeIcons, handleCancelRename, handleContextMenu, handleCopy, handleCreateFolder, handleCreateMultiChatRoom, handleCreateProject, handleDragEnd, handleDragStart, handleDropOnTrash, handleEditSwitch, handleEmptyTrash, handleExecuteSwitch, handleFinishRename, handleItemContextMenu, handleMoveToFolder, handleOpenCalendar, handleOpenMultiChatRoom, handleOpenProject, handleOpenScheduler, handleOpenSettings, handleOpenTrash, handlePaste, handlePositionChange, handleRestoreFromTrash, handleSaveSwitchEdit, handleSaveSystemAi, handleSelect, handleStartRename, hoveringFolderId, isLoading, launcherTab, lightweightAiSettings, loadMultiChatRooms, loadPromoted, loadTrashItems, logoImage, mainMenuRef, midtierAiSettings, mobileToolsOpen, modeMenuRef, multiChatRooms, newFolderName, newMultiChatName, newProjectName, openSystemAI, openTool, pendingBrowserUrl, projectQuery, promotedApps, renamingItem, retryLauncherData, schedulerTasks, selectMode, selectPromoted, selectedItem, sendClipboardToPhone, setBrowserOpen, setContextMenu, setEditingSwitchData, setHoveringFolderId, setLightweightAiSettings, setMidtierAiSettings, setMobileToolsOpen, setMultiChatRooms, setNewFolderName, setNewMultiChatName, setNewProjectName, setPendingBrowserUrl, setProjectQuery, setShowApiKey, setShowGuideDialog, setShowLightweightApiKey, setShowMainMenu, setShowMidtierApiKey, setShowModeMenu, setShowNewFolderDialog, setShowNewMultiChatDialog, setShowNewProjectDialog, setShowOnboardingDialog, setShowSchedulerDialog, setShowSettingsDialog, setShowSwitchEditDialog, setShowTrashDialog, setShowUserManualDialog, setSwitchEditForm, setSystemAiSettings, setTrashPosition, showApiKey, showGuideDialog, showGuideOnce, showLightweightApiKey, showMainMenu, showMidtierApiKey, showModeMenu, showNewFolderDialog, showNewMultiChatDialog, showNewProjectDialog, showOnboardingDialog, showSchedulerDialog, showSettingsDialog, showSwitchEditDialog, showTrashDialog, showUserManualDialog, showingApp, staticAppLabel, switchEditForm, systemAiSettings, toolNavigation, trashHover, trashItems, trashPosition, trashRef, ui, window } = bindings;
  return (
    <div className="launcher-root h-full flex flex-col bg-[#F5F1EB]">
      {IS_WEB_SURFACE && <div className="remote-mobile-only mobile-launcher-heading">
        <span className="font-semibold text-stone-800">{showingApp ? staticAppLabel({id: activeAppId!, ...activeMeta!}) : <UiText id={MODE_META[launcherTab].label} />}</span>
        <button onClick={openSystemAI} className="ml-auto rounded-xl bg-amber-600 text-white px-3 flex items-center gap-2"><Bot size={18} /> 시스템 AI</button>
        <button onClick={() => setMobileToolsOpen(v => !v)} aria-expanded={mobileToolsOpen} aria-controls="launcher-tools" className="rounded-xl border border-stone-300 px-3">{mobileToolsOpen ? '접기' : '더보기'}</button>
      </div>}
      {/* 상단 툴바 */}
      <div id="launcher-tools" className={`launcher-toolbar ${mobileToolsOpen ? 'mobile-tools-open' : ''} min-h-11 shrink-0 flex items-center justify-end px-4 drag bg-gradient-to-b from-[#F7F3ED] to-[#F5F1EB] border-b border-[#E5DFD5]`}>
        <div className="flex flex-wrap justify-end items-center gap-1.5 no-drag whitespace-nowrap">
          <LanguagePicker />
          {/* 모드 선택기 — 네 표면(자율주행/조종실/앱/공유창고)을 오간다. X-Ray 앞. */}
          <div className="relative" ref={modeMenuRef}>
            <button
              onClick={() => setShowModeMenu((v) => { if (!v) loadPromoted().catch(() => {}); return !v; })}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-colors text-[#6B5B4F] ${showModeMenu ? 'bg-[#EAE4DA]' : 'hover:bg-[#EAE4DA] active:bg-[#E0D9CC]'}`}
              title="화면 모드 선택"
              aria-haspopup="true"
              aria-expanded={showModeMenu}
            >
              {showingApp
                ? <span className="text-[15px] leading-none">{activeMeta!.icon}</span>
                : <ActiveModeIcon size={15} />}
              <span className="text-[13px] font-medium">{showingApp ? staticAppLabel({id: activeAppId!, ...activeMeta!}) : <UiText id={MODE_META[launcherTab].label} />}</span>
              <ChevronDown size={12} className={`transition-transform ${showModeMenu ? 'rotate-180' : ''}`} />
            </button>
            {showModeMenu && (
              <div className="absolute left-0 top-full mt-2 bg-white rounded-xl shadow-xl border border-stone-200 py-1.5 min-w-[190px] z-50 overflow-hidden">
                {LAUNCHER_MODES.map((m) => {
                  const Icon = MODE_META[m].icon;
                  const active = launcherTab === m && !(m === 'app' && showingApp);
                  return (
                    <button
                      key={m}
                      onClick={() => selectMode(m)}
                      className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${active ? 'bg-amber-50 text-amber-900' : 'text-[#4A4035] hover:bg-amber-50'}`}
                    >
                      <Icon size={16} className={active ? 'text-amber-600' : 'text-stone-500'} />
                      <span className="text-sm"><UiText id={MODE_META[m].label} /></span>
                    </button>
                  );
                })}
                {/* 구분선 아래 = 앱 모드에서 승격한 앱들. 선택하면 그 앱이 바로 열린다. */}
                {promotedApps.length > 0 && (
                  <>
                    <div className="border-t border-stone-100 my-1" />
                    {promotedApps.map((app) => {
                      const active = showingApp && activeAppId === app.id;
                      return (
                        <div
                          key={app.id}
                          className={`group flex items-center transition-colors ${active ? 'bg-amber-50' : 'hover:bg-amber-50'}`}
                        >
                          <button
                            onClick={() => selectPromoted(app.id)}
                            className={`flex-1 min-w-0 flex items-center gap-3 pl-4 pr-2 py-2.5 text-left ${active ? 'text-amber-900' : 'text-[#4A4035]'}`}
                          >
                            <span className="text-base leading-none w-4 text-center">{app.icon}</span>
                            <span className="text-sm truncate">{staticAppLabel(app)}</span>
                          </button>
                          <button
                            onClick={() => demotePromoted(app.id)}
                            title="런처에서 빼기"
                            aria-label={`${app.label} 런처에서 빼기`}
                            className="shrink-0 mr-2 p-1 rounded-md text-stone-300 hover:text-red-600 hover:bg-red-50 transition-colors"
                          >
                            <X size={14} />
                          </button>
                        </div>
                      );
                    })}
                  </>
                )}
              </div>
            )}
          </div>

          <div className="w-px h-5 bg-[#D8D1C3] mx-1" aria-hidden="true" />

          {/* 그룹 A: 세계 / 감각 */}
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => {
                // 외부 브라우저 대신 검색 브라우저(포식) 오버레이의 한 탭으로 X-Ray 대시보드를 연다.
                setBrowserOpen(true);
                setPendingBrowserUrl(`${BACKEND_ORIGIN}/xray/app`);
              }}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg hover:bg-[#EAE4DA] active:bg-[#E0D9CC] transition-colors text-[#6B5B4F]"
              title="System X-Ray - 시스템 상태를 검색 브라우저 탭으로 연다"
            >
              <ScanLine size={15} />
              <span className="text-[13px]">X-Ray</span>
            </button>
            <button
              onClick={() => {
                // 커뮤니티 서비스(옛 IndieNet) — 표면과 무관하게 전용 창으로 진입.
                // 내용은 앱모드와 동일한 IBL 커뮤니티 계기(피드·게시판·내 계정).
                if (window.electron?.openCommunityWindow) {
                  window.electron.openCommunityWindow();
                } else {
                  window.location.hash = '#/community';  // 브라우저 폴백
                }
              }}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg hover:bg-[#EAE4DA] active:bg-[#E0D9CC] transition-colors text-[#6B5B4F]"
              title="IndieNet 커뮤니티"
            >
              <Globe size={15} />
              <span className="text-[13px]">IndieNet</span>
            </button>
          </div>

          <div className="w-px h-5 bg-[#D8D1C3] mx-1" aria-hidden="true" />

          {/* 그룹 B: 소통 */}
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => {
                // 메신저(=이웃관리 CRM) — 표면과 무관하게 전용 창으로 진입.
                // 옛 빠른 연락처(ContactsDialog)·이웃관리 창(NeighborManagerDialog)을 대체.
                if (window.electron?.openMessengerWindow) {
                  window.electron.openMessengerWindow();
                } else {
                  window.location.hash = '#/messenger';  // 브라우저 폴백
                }
              }}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg hover:bg-[#EAE4DA] active:bg-[#E0D9CC] transition-colors text-[#6B5B4F]"
              title="메신저 — 대화 · 이웃 관리 (레벨·연락처)"
            >
              <Contact size={15} />
              <span className="text-[13px]">메신저</span>
            </button>
            <button
              onClick={sendClipboardToPhone}
              disabled={clipToPhone === 'sending'}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-colors ${
                clipToPhone === 'ok' || clipToPhone === 'queued'
                  ? 'text-emerald-700 bg-emerald-50'
                  : clipToPhone === 'err'
                    ? 'text-red-600 bg-red-50'
                    : 'text-[#6B5B4F] hover:bg-[#EAE4DA] active:bg-[#E0D9CC]'
              }`}
              title="맥 클립보드를 폰으로 — 지금 복사(⌘C)된 내용을 폰 클립보드에 넣고 알림을 띄웁니다 (Wi-Fi 직결, LTE 여도 푸시 큐로 전달)"
            >
              <Smartphone size={15} />
              <span className="text-[13px]">
                {clipToPhone === 'idle' && '폰으로'}
                {clipToPhone === 'sending' && '보내는 중…'}
                {clipToPhone === 'ok' && '복사됨 ✓'}
                {clipToPhone === 'queued' && '전달됨 ✓'}
                {clipToPhone === 'err' && '실패'}
              </span>
            </button>
            <button
              onClick={openSystemAI}
              className="ml-1 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-br from-amber-500 to-amber-600 text-white shadow-sm hover:shadow-md hover:from-amber-600 hover:to-amber-700 active:translate-y-[0.5px] transition-all"
              title="시스템 AI와 대화"
            >
              <Bot size={15} />
              <span className="text-[13px] font-semibold">시스템 AI</span>
            </button>
          </div>

          <div className="w-px h-5 bg-[#D8D1C3] mx-1" aria-hidden="true" />

          {/* 메인 메뉴 (드롭다운) — 예약작업 등 관리 항목을 펼친다 */}
          <div className="relative" ref={mainMenuRef}>
            <button
              onClick={() => setShowMainMenu(!showMainMenu)}
              className={`flex items-center gap-1 px-1.5 py-1 rounded-lg transition-all text-[#6B5B4F] ${
                showMainMenu ? 'bg-[#EAE4DA]' : 'hover:bg-[#EAE4DA]'
              }`}
              title="메뉴"
              aria-expanded={showMainMenu}
              aria-haspopup="true"
            >
              <img src={logoImage} alt="IndieBiz" className="w-9 h-9 object-contain" style={{ mixBlendMode: 'multiply' }} />
              <ChevronDown size={12} className={`transition-transform ${showMainMenu ? 'rotate-180' : ''}`} />
            </button>

            {showMainMenu && (
              <div className="absolute right-0 top-full mt-2 bg-white rounded-xl shadow-xl border border-stone-200 py-1.5 min-w-[200px] z-50 overflow-hidden">
                {IS_WEB_SURFACE && <>
                  <button onClick={() => { setShowNewProjectDialog(true); setShowMainMenu(false); }} className="block w-full px-4 py-2.5 text-left text-sm hover:bg-amber-50">새 프로젝트</button>
                  <button onClick={() => { setShowNewFolderDialog(true); setShowMainMenu(false); }} className="block w-full px-4 py-2.5 text-left text-sm hover:bg-amber-50">새 폴더</button>
                  <button onClick={() => { setShowNewMultiChatDialog(true); setShowMainMenu(false); }} className="block w-full px-4 py-2.5 text-left text-sm hover:bg-amber-50">새 다중채팅방</button>
                  <div className="border-t border-stone-100 my-1" />
                </>}
                <button
                  onClick={() => {
                    handleOpenScheduler();
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors"
                >
                  <Clock size={16} className="text-stone-500" />
                  <span className="text-sm">예약작업</span>
                </button>
                <div className="border-t border-stone-100 my-1" />
                <button
                  onClick={() => {
                    handleOpenSettings();
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors"
                >
                  <Settings size={16} className="text-stone-500" />
                  <span className="text-sm">설정</span>
                </button>
                {Object.entries(toolNavigation).filter(([, item]) => 'menuIcon' in item).map(([id, item]) => {
                  const icons = { Laptop, Users, Boxes, Layers, FileText };
                  const Icon = icons[(item as { menuIcon: keyof typeof icons }).menuIcon];
                  return <button key={id} onClick={() => { openTool(id as keyof typeof toolNavigation); setShowMainMenu(false); }}
                    className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors">
                    <Icon size={16} className="text-stone-500" /><span className="text-sm">{ui.source('navigation', item.title)}</span>
                  </button>;
                })}
                <div className="border-t border-stone-100 my-1" />
                <button
                  onClick={() => {
                    setShowGuideDialog(true);
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors"
                >
                  <HelpCircle size={16} className="text-stone-500" />
                  <span className="text-sm">시작 가이드</span>
                </button>
                <button
                  onClick={() => {
                    setShowUserManualDialog(true);
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors"
                >
                  <BookOpen size={16} className="text-stone-500" />
                  <span className="text-sm">사용자 메뉴얼</span>
                </button>
                <button
                  onClick={() => {
                    alert(`IndieBiz OS\n버전: 1.0.0\n\n개인과 소규모 비즈니스를 위한 AI 운영체제`);
                    setShowMainMenu(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-amber-50 text-left text-[#4A4035] transition-colors"
                >
                  <Info size={16} className="text-stone-500" />
                  <span className="text-sm">버전 정보</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 데스크탑 + 포식 오버레이를 한 relative 래퍼로 — 포식 브라우저가 전체를 덮을 수 있게.
          (옛 자율주행/조종실/앱 3토글은 상단 툴바의 모드 선택기로 대체됨) */}
      <div className="relative flex-1 flex flex-col min-h-0">
      {/* 데스크탑 영역 */}
      <div
        ref={desktopRef}
        className="flex-1 relative overflow-hidden"
        onContextMenu={handleContextMenu}
      >
        {launcherTab === 'app' ? (
          // key 에 activeAppId 를 넣어 승격 앱 전환 시 깨끗이 remount(딥링크 재적용).
          // openNonce 는 '같은 앱 재선택'을 위한 신호 — remount 없이도 열기가 다시 돈다.
          <ActionDesktop key={`app:${activeAppId || ''}`} openAppId={activeAppId} openNonce={appOpenNonce} />
        ) : launcherTab === 'warehouse' ? (
          <WarehouseView />
        ) : launcherTab === 'manual' ? (
          <ManualMode />
        ) : isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#D97706]" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full text-[#B45309]">
            <p>{error}</p>
            <button
              onClick={retryLauncherData}
              className="mt-4 px-4 py-2 bg-[#FEF3C7] rounded-lg hover:bg-[#FDE68A] text-[#92400E]"
            >
              다시 시도
            </button>
          </div>
        ) : IS_WEB_SURFACE ? (
          <div className="h-full overflow-auto p-4">
            <label className="block mb-4">
              <span className="sr-only">프로젝트·스위치·대화 찾기</span>
              <input type="search" value={projectQuery} onChange={e => setProjectQuery(e.target.value)} placeholder="프로젝트·스위치·대화 찾기" className="w-full rounded-xl border border-stone-200 bg-white px-3 py-3 text-sm" />
            </label>
            <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-8 gap-4">
              {displayProjects.filter(p => p.name.toLocaleLowerCase().includes(projectQuery.trim().toLocaleLowerCase())).map(project => <button key={project.id} onClick={() => handleOpenProject(project)}
                className="p-3 rounded-xl hover:bg-white flex flex-col items-center gap-2 min-w-0">
                <span className="text-3xl">{project.type === 'folder' ? '📂' : '📁'}</span>
                <span className="text-xs break-all">{project.name}</span>
              </button>)}
              {displaySwitches.filter(sw => sw.name.toLocaleLowerCase().includes(projectQuery.trim().toLocaleLowerCase())).map(sw => <button key={sw.id} onClick={() => handleExecuteSwitch(sw)}
                className="p-3 rounded-xl hover:bg-white flex flex-col items-center gap-2 min-w-0">
                <span className="text-3xl">⚡</span><span className="text-xs break-all">{sw.name}</span>
              </button>)}
              {multiChatRooms.filter(room => room.name.toLocaleLowerCase().includes(projectQuery.trim().toLocaleLowerCase())).map(room => <button key={room.id} onClick={() => handleOpenMultiChatRoom(room)}
                className="p-3 rounded-xl hover:bg-white flex flex-col items-center gap-2 min-w-0">
                <span className="text-3xl">💬</span><span className="text-xs break-all">{room.name}</span>
              </button>)}
              <button onClick={handleOpenTrash} className="p-3 rounded-xl hover:bg-white text-sm">🗑️ 휴지통</button>
            </div>
          </div>
        ) : (
          <>
            {/* 프로젝트 아이콘들 */}
            {displayProjects.map((project) => (
              <DraggableIcon
                key={project.id}
                icon={project.type === 'folder' ? <Folder size={40} /> : project.project_kind === 'research' ? '📚' : '📁'}
                label={project.name}
                position={project.icon_position}
                onDoubleClick={() => handleOpenProject(project)}
                onPositionChange={(x, y) =>
                  handlePositionChange(project.id, 'project', x, y)
                }
                onDragStart={() => handleDragStart(project.id, 'project')}
                onDragEnd={() => {
                  handleDragEnd();
                  setHoveringFolderId(null);
                }}
                onDragMove={(x, y) => {
                  checkTrashHover(x, y);
                  checkFolderHover(x, y, project.id);
                  return trashHover;
                }}
                onDropOnTrash={handleDropOnTrash}
                onDropOnFolder={(folderId) => handleMoveToFolder(project.id, folderId)}
                trashHover={trashHover}
                isFolder={project.type === 'folder'}
                whiteTile={project.type !== 'folder'}
                isFolderHovered={hoveringFolderId === project.id}
                folderRef={(el) => {
                  if (project.type === 'folder') {
                    folderRefs.current[project.id] = el;
                  }
                }}
                hoveringFolderId={hoveringFolderId}
                onContextMenu={(e) => handleItemContextMenu(e, project.id, 'project')}
                onSelect={() => handleSelect(project.id, 'project')}
                isSelected={selectedItem?.id === project.id && selectedItem?.type === 'project'}
                isRenaming={renamingItem?.id === project.id && renamingItem?.type === 'project'}
                onFinishRename={handleFinishRename}
                onCancelRename={handleCancelRename}
              />
            ))}

            {/* 스위치 아이콘들 */}
            {displaySwitches.map((sw) => (
              <DraggableIcon
                key={sw.id}
                icon={sw.icon || <Zap size={40} />}
                label={sw.name}
                position={sw.icon_position}
                onDoubleClick={() => handleExecuteSwitch(sw)}
                onPositionChange={(x, y) =>
                  handlePositionChange(sw.id, 'switch', x, y)
                }
                onDragStart={() => handleDragStart(sw.id, 'switch')}
                onDragEnd={() => {
                  handleDragEnd();
                  setHoveringFolderId(null);
                }}
                onDragMove={(x, y) => {
                  checkTrashHover(x, y);
                  return trashHover;
                }}
                onDropOnTrash={handleDropOnTrash}
                trashHover={trashHover}
                isSwitch
                onContextMenu={(e) => handleItemContextMenu(e, sw.id, 'switch')}
                onSelect={() => handleSelect(sw.id, 'switch')}
                isSelected={selectedItem?.id === sw.id && selectedItem?.type === 'switch'}
                isRenaming={renamingItem?.id === sw.id && renamingItem?.type === 'switch'}
                onFinishRename={handleFinishRename}
                onCancelRename={handleCancelRename}
              />
            ))}

            {/* 다중채팅방 아이콘들 */}
            {multiChatRooms.map((room) => (
              <DraggableIcon
                key={room.id}
                icon={<Users size={40} className="text-purple-500" />}
                label={room.name}
                position={room.icon_position || [600, 100]}
                onDoubleClick={() => handleOpenMultiChatRoom(room)}
                onPositionChange={async (x, y) => {
                  // 로컬 상태 업데이트
                  setMultiChatRooms(prev => prev.map(r =>
                    r.id === room.id ? { ...r, icon_position: [x, y] as [number, number] } : r
                  ));
                  // 서버에 위치 저장
                  try {
                    await api.updateMultiChatRoomPosition(room.id, x, y);
                  } catch (error) {
                    console.error('Failed to update multi-chat room position:', error);
                  }
                }}
                onDragStart={() => handleDragStart(room.id, 'project')}
                onDragEnd={() => {
                  handleDragEnd();
                }}
                onDragMove={(x, y) => {
                  checkTrashHover(x, y);
                  return trashHover;
                }}
                onDropOnTrash={async () => {
                  // 다중채팅방을 휴지통으로 이동
                  try {
                    await api.moveMultiChatRoomToTrash(room.id);
                    loadMultiChatRooms();
                    loadTrashItems();
                  } catch (error) {
                    console.error('Failed to move multi-chat room to trash:', error);
                  }
                }}
                trashHover={trashHover}
                isMultiChat
              />
            ))}

            {/* 휴지통 아이콘 - 드래그 가능 */}
            <DraggableTrash
              trashRef={trashRef}
              trashHover={trashHover}
              position={trashPosition}
              onPositionChange={(x, y) => setTrashPosition({ x, y })}
              onDoubleClick={handleOpenTrash}
              onContextMenu={(e) => {
                e.preventDefault();
                setContextMenu({ x: e.clientX, y: e.clientY, itemId: '__trash__', itemType: 'project' });
              }}
              trashCount={trashItems.projects.length + trashItems.switches.length + (trashItems.chat_rooms?.length || 0)}
            />
          </>
        )}
      </div>

        {/* 포식 브라우저 — 앱모드의 앱(forage 타일)이자 X-Ray·타 창 URL의 착지점. 상시 마운트해
            탭·사냥판 상태를 보존하고 open 으로 표시/숨김만 토글한다. ✕닫기는 현재 표면으로 복귀(오버레이). */}
        <ForageBrowser
          open={browserOpen}
          onClose={() => setBrowserOpen(false)}
          openUrl={pendingBrowserUrl}
          onUrlConsumed={() => setPendingBrowserUrl(null)}
        />
      </div>

      {IS_WEB_SURFACE && <nav aria-label="런처 모드" className="remote-mobile-only mobile-mode-nav">
        {(['autopilot', 'manual', 'app', 'warehouse'] as const).map(mode => {
          const Icon = MODE_META[mode].icon;
          return <button key={mode} aria-current={launcherTab === mode ? 'page' : undefined}
            onClick={() => { selectMode(mode); setMobileToolsOpen(false); setBrowserOpen(false); }}>
            <Icon size={21} /><span><UiText id={MODE_META[mode].label} /></span>
          </button>;
        })}
      </nav>}

      {/* 컨텍스트 메뉴 */}
      <ContextMenu
        contextMenu={contextMenu}
        clipboard={clipboard}
        onClose={closeContextMenu}
        onRename={handleStartRename}
        onCopy={handleCopy}
        onPaste={handlePaste}
        onNewProject={() => setShowNewProjectDialog(true)}
        onNewFolder={() => setShowNewFolderDialog(true)}
        onNewMultiChatRoom={() => setShowNewMultiChatDialog(true)}
        onOpenTrash={handleOpenTrash}
        onEmptyTrash={handleEmptyTrash}
        onArrangeIcons={handleArrangeIcons}
        getItemName={getItemName}
        onEditSwitch={handleEditSwitch}
      />

      {/* 새 프로젝트 다이얼로그 */}
      <NewProjectDialog
        show={showNewProjectDialog}
        name={newProjectName}
        onNameChange={setNewProjectName}
        onSubmit={handleCreateProject}
        onClose={() => setShowNewProjectDialog(false)}
      />

      {/* 새 폴더 다이얼로그 */}
      <NewFolderDialog
        show={showNewFolderDialog}
        name={newFolderName}
        onNameChange={setNewFolderName}
        onSubmit={handleCreateFolder}
        onClose={() => setShowNewFolderDialog(false)}
      />

      {/* 새 다중채팅방 다이얼로그 */}
      {showNewMultiChatDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-96 shadow-xl">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Users size={20} className="text-purple-500" />
              새 다중채팅방
            </h2>
            <input
              type="text"
              value={newMultiChatName}
              onChange={(e) => setNewMultiChatName(e.target.value)}
              placeholder="채팅방 이름"
              className="w-full px-4 py-2 border rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-purple-500 text-gray-900"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateMultiChatRoom();
                if (e.key === 'Escape') setShowNewMultiChatDialog(false);
              }}
            />
            <p className="text-sm text-gray-500 mb-4">
              여러 에이전트와 동시에 대화할 수 있는 토론방입니다.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowNewMultiChatDialog(false)}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleCreateMultiChatRoom}
                className="px-4 py-2 bg-purple-500 text-white hover:bg-purple-600 rounded-lg transition-colors"
              >
                만들기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 설정 다이얼로그 */}
      <SettingsDialog
        show={showSettingsDialog}
        settings={systemAiSettings}
        showApiKey={showApiKey}
        onSettingsChange={setSystemAiSettings}
        onToggleApiKey={() => setShowApiKey(!showApiKey)}
        lightweightSettings={lightweightAiSettings}
        showLightweightApiKey={showLightweightApiKey}
        onLightweightSettingsChange={setLightweightAiSettings}
        onToggleLightweightApiKey={() => setShowLightweightApiKey(!showLightweightApiKey)}
        midtierSettings={midtierAiSettings}
        showMidtierApiKey={showMidtierApiKey}
        onMidtierSettingsChange={setMidtierAiSettings}
        onToggleMidtierApiKey={() => setShowMidtierApiKey(!showMidtierApiKey)}
        onSave={handleSaveSystemAi}
        onClose={() => setShowSettingsDialog(false)}
      />

      {/* 휴지통 다이얼로그 */}
      <TrashDialog
        show={showTrashDialog}
        trashItems={trashItems}
        onRestore={handleRestoreFromTrash}
        onEmpty={handleEmptyTrash}
        onClose={() => setShowTrashDialog(false)}
      />

      {/* 예약작업 다이얼로그 (읽기 전용) */}
      <SchedulerDialog
        show={showSchedulerDialog}
        tasks={schedulerTasks}
        formatLastRun={formatLastRun}
        onClose={() => setShowSchedulerDialog(false)}
        onOpenCalendar={handleOpenCalendar}
      />

      {/* 스위치 편집 다이얼로그 */}
      <SwitchEditDialog
        show={showSwitchEditDialog}
        switchData={editingSwitchData}
        form={switchEditForm}
        onFormChange={setSwitchEditForm}
        onSave={handleSaveSwitchEdit}
        onClose={() => {
          setShowSwitchEditDialog(false);
          setEditingSwitchData(null);
        }}
      />

      {/* 첫 성공 온보딩 — 닫히면(완료든 건너뜀이든) 가이드로 이어진다 */}
      <OnboardingDialog
        show={showOnboardingDialog}
        onClose={() => { setShowOnboardingDialog(false); showGuideOnce(); }}
      />

      {/* 시작 가이드 다이얼로그 */}
      <GuideDialog
        show={showGuideDialog}
        onClose={() => setShowGuideDialog(false)}
      />

      {/* 사용자 메뉴얼 다이얼로그 */}
      <UserManualDialog
        show={showUserManualDialog}
        onClose={() => setShowUserManualDialog(false)}
      />
    </div>
  );
}
