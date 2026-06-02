import os
import glob
from datetime import datetime

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    try:
        if tool_name == "read_file":
            path = os.path.join(project_path, tool_input["file_path"])
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()

        elif tool_name == "write_file":
            path = os.path.join(project_path, tool_input["file_path"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(tool_input["content"])
            return f"Successfully wrote to {tool_input['file_path']}"

        elif tool_name == "list_directory":
            dir_path = os.path.join(project_path, tool_input.get("dir_path", "."))
            items = os.listdir(dir_path)
            return "\n".join(items)

        elif tool_name == "search_files":
            search_type = tool_input["search_type"]
            query = tool_input["query"]
            root = os.path.join(project_path, tool_input.get("root_path", "."))
            results = []

            if search_type == "name":
                for r, d, f in os.walk(root):
                    for file in f:
                        if query in file:
                            results.append(os.path.relpath(os.path.join(r, file), project_path))
            
            elif search_type == "content":
                for r, d, f in os.walk(root):
                    for file in f:
                        full_path = os.path.join(r, file)
                        try:
                            with open(full_path, 'r', encoding='utf-8') as f_obj:
                                if query in f_obj.read():
                                    results.append(os.path.relpath(full_path, project_path))
                        except:
                            continue
            return "\n".join(results) if results else "No matches found."

        elif tool_name == "get_current_time":
            fmt = tool_input.get("format", "%Y-%m-%d %H:%M:%S")
            return datetime.now().strftime(fmt)

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Error: {str(e)}"
