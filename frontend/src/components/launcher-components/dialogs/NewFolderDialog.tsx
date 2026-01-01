/**
 * NewFolderDialog - 새 폴더 생성 다이얼로그
 */

interface NewFolderDialogProps {
  show: boolean;
  name: string;
  onNameChange: (name: string) => void;
  onSubmit: () => void;
  onClose: () => void;
}

export function NewFolderDialog({
  show,
  name,
  onNameChange,
  onSubmit,
  onClose,
}: NewFolderDialogProps) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-96 shadow-2xl">
        <h2 className="text-xl font-bold mb-4 text-gray-800">새 폴더</h2>
        <input
          type="text"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="폴더 이름"
          className="w-full px-4 py-2 bg-gray-50 rounded-lg border border-gray-300 focus:border-blue-500 focus:outline-none text-gray-800"
          autoFocus
          onKeyDown={(e) => {
            if (e.key === 'Enter') onSubmit();
            if (e.key === 'Escape') onClose();
          }}
        />
        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-600"
          >
            취소
          </button>
          <button
            onClick={onSubmit}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            생성
          </button>
        </div>
      </div>
    </div>
  );
}
