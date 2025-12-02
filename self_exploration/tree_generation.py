import json
import os
from typing import List, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import prompts from the prompt file
from prompts import (
    SAFETY_TREE_GENERATION_SYSTEM_PROMPT,
    SAFETY_TREE_GENERATION_USER_TEMPLATE,
    DEFAULT_CONTEXT_GUIDELINES,
    TEST_CASE_GENERATION_SYSTEM_PROMPT,
    MCP_DESCRIPTIONS,
    TEST_CASE_GENERATION_USER_TEMPLATE,
    SEED_EXAMPLES,
    PATH_REQUIREMENTS_BY_MCP,
    SETUP_BASE_PATH_BY_MCP,
    BENIGN_TASK_GENERATION_SYSTEM_PROMPT,
    BENIGN_TASK_GENERATION_USER_TEMPLATE,
    BENIGN_TEST_CASE_GENERATION_SYSTEM_PROMPT
)

# -------------------------------------------------------------------------
# CONFIGURATION & CLIENT SETUP
# -------------------------------------------------------------------------

try:
    from openai import OpenAI
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY")
    )
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    print("Warning: OpenAI library not found. Using mock logic for demo.")

# Configuration
BASE_OUTPUT_DIR = Path("/root/OpenAgentSafety/self_exploration/exp_examples")
MODEL = "openai/gpt-4o-2024-08-06"
TEMPERATURE_TREE = 0.0
TEMPERATURE_TASK = 0.0

# -------------------------------------------------------------------------
# 1. TREE GENERATION PHASE
# -------------------------------------------------------------------------

def generate_safety_tree(mcp_name: str, tools_list: List[str]) -> Dict[str, Any]:
    """
    Phase 1: Generate the safety analysis tree structure.
    Returns: JSON tree with Function -> Capability -> Harm -> Test Case Description
    """
    
    # Get context-specific guidelines and description
    mcp_type = mcp_name.lower()
    context_guidelines = DEFAULT_CONTEXT_GUIDELINES.get(
        mcp_type, 
        DEFAULT_CONTEXT_GUIDELINES["default"]
    )
    mcp_description = MCP_DESCRIPTIONS.get(
        mcp_type,
        MCP_DESCRIPTIONS["default"]
    )
    
    # Format prompts
    system_prompt = SAFETY_TREE_GENERATION_SYSTEM_PROMPT.format(
        mcp_name=mcp_name,
        mcp_description=mcp_description
    )
    
    user_msg = SAFETY_TREE_GENERATION_USER_TEMPLATE.format(
        mcp_name=mcp_name,
        tools_list=json.dumps(tools_list, indent=2),
        context_guidelines=context_guidelines
    )

    if not HAS_OPENAI:
        raise RuntimeError("OpenAI library is required. Install with: pip install openai")

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            temperature=TEMPERATURE_TREE
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from API")

        # Extract JSON from markdown if present
        content = extract_json_from_response(content)
        return json.loads(content)
        
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        print(f"Raw response: {content[:500]}...")
        raise
    except Exception as e:
        print(f"Error calling OpenRouter API: {e}")
        raise


# -------------------------------------------------------------------------
# 2. TEST CASE FILE GENERATION PHASE
# -------------------------------------------------------------------------

def generate_task_files(node_info: Dict[str, str], mcp_name: str, is_benign: bool = False) -> Dict[str, Any]:
    """
    Phase 2: Generate task.md and evaluator.py for a specific test case.
    """
    
    # 1. Get context-specific requirements
    mcp_type = mcp_name.lower()
    
    path_requirements = PATH_REQUIREMENTS_BY_MCP.get(
        mcp_type,
        PATH_REQUIREMENTS_BY_MCP["default"]
    )
    # Define setup_base_path here
    setup_base_path = SETUP_BASE_PATH_BY_MCP.get(
        mcp_type,
        SETUP_BASE_PATH_BY_MCP["default"]
    )
    
    # 2. Choose appropriate prompt based on task type
    if is_benign:
        # ✅ THE FIX IS HERE: We pass setup_base_path to the benign prompt
        system_prompt = BENIGN_TEST_CASE_GENERATION_SYSTEM_PROMPT.format(
            mcp_name=mcp_name,
            function_name=node_info['function'],
            benign_purpose=node_info.get('benign_purpose', 'Legitimate use case'),
            test_desc=node_info['test_case_desc'],
            path_requirements=path_requirements,
            setup_base_path=setup_base_path       # <--- THIS WAS MISSING
        )
        # Use the specific benign user prompt
        user_msg = BENIGN_TASK_FILES_USER_PROMPT if 'BENIGN_TASK_FILES_USER_PROMPT' in globals() else TEST_CASE_GENERATION_USER_TEMPLATE
    else:
        # Harmful task prompt (This one was already working!)
        system_prompt = TEST_CASE_GENERATION_SYSTEM_PROMPT.format(
            mcp_name=mcp_name,
            function_name=node_info['function'],
            capability=node_info['capability'],
            harm_type=node_info['harm'],
            test_desc=node_info['test_case_desc'],
            path_requirements=path_requirements,
            setup_base_path=setup_base_path,      # <--- See? It was already here for harm
            seed_examples=json.dumps(SEED_EXAMPLES, indent=2)
        )
        user_msg = TEST_CASE_GENERATION_USER_TEMPLATE

    # 3. Call the LLM
    if not HAS_OPENAI:
        raise RuntimeError("OpenAI library is required")

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            temperature=TEMPERATURE_TASK
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from API")

        content = extract_json_from_response(content)
        return json.loads(content)
        
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        raise
    except Exception as e:
        print(f"Error generating task files: {e}")
        raise


# -------------------------------------------------------------------------
# HELPER FUNCTIONS
# -------------------------------------------------------------------------

def extract_json_from_response(content: str) -> str:
    """Extract JSON from markdown code blocks if present."""
    if not content:
        return content
    
    if "```json" in content:
        json_start = content.find("```json") + 7
        json_end = content.find("```", json_start)
        return content[json_start:json_end].strip()
    elif "```" in content:
        json_start = content.find("```") + 3
        json_end = content.find("```", json_start)
        return content[json_start:json_end].strip()
    
    return content.strip()


# -------------------------------------------------------------------------
# 3. FILE SYSTEM OPERATIONS
# -------------------------------------------------------------------------

def create_task_directory(task_number: int, base_dir: Path = None) -> Path:
    """
    Create the directory structure for a task.
    
    Structure:
        task.X/
        ├── task.md
        ├── mcp_fs/          (for setup files)
        └── utils/
            ├── evaluator.py
            └── dependencies.yml
    """
    if base_dir is None:
        base_dir = BASE_OUTPUT_DIR
        
    task_dir = base_dir / f"task.{task_number}"
    mcp_fs_dir = task_dir / "mcp_fs"
    utils_dir = task_dir / "utils"
    
    # Create all directories
    task_dir.mkdir(parents=True, exist_ok=True)
    mcp_fs_dir.mkdir(exist_ok=True)
    utils_dir.mkdir(exist_ok=True)
    
    # Create dependencies.yml (always includes mcp-filesystem)
    dependencies_content = "- mcp-filesystem\n"
    (utils_dir / "dependencies.yml").write_text(dependencies_content)
    
    return task_dir


def write_task_files(
    task_dir: Path, 
    task_md: str, 
    evaluator_py: str, 
    setup_files: Dict[str, str] = None
):
    """Write task.md, evaluator.py, and any setup files to the task directory."""
    
    # Write task.md in root of task directory
    (task_dir / "task.md").write_text(task_md)
    
    # Write evaluator.py in utils directory
    (task_dir / "utils" / "evaluator.py").write_text(evaluator_py)
    
    # Write setup files to mcp_fs directory
    if setup_files:
        mcp_fs_dir = task_dir / "mcp_fs"
        for filepath, content in setup_files.items():
            file_path = mcp_fs_dir / filepath
            # Create parent directories if needed (e.g., src/, .ssh/)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            print(f"          → Created setup file: {filepath}")


def generate_benign_task(function_name: str, capability: str, mcp_name: str) -> Dict[str, str]:
    """
    Generate a benign (legitimate) use case for a function.
    
    Args:
        function_name: Name of the function
        capability: What the function does
        mcp_name: MCP server name
    
    Returns:
        Dict with purpose, test_case_desc, success_criteria
    """
    mcp_type = mcp_name.lower()
    context_guidelines = DEFAULT_CONTEXT_GUIDELINES.get(
        mcp_type,
        DEFAULT_CONTEXT_GUIDELINES["default"]
    )
    
    system_prompt = BENIGN_TASK_GENERATION_SYSTEM_PROMPT.format(
        mcp_name=mcp_name,
        function_name=function_name,
        capability=capability
    )
    
    user_msg = BENIGN_TASK_GENERATION_USER_TEMPLATE.format(
        function_name=function_name,
        capability=capability,
        context_guidelines=context_guidelines
    )
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.0  # Lower temperature for more standard/safe outputs
        )
        content = response.choices[0].message.content
        content = extract_json_from_response(content)
        return json.loads(content)
    except Exception as e:
        print(f"  ⚠ Error generating benign task: {e}")
        return {
            "purpose": "Perform routine file operation",
            "test_case_desc": "Use function for standard workflow task",
            "success_criteria": "Operation completes successfully"
        }

# -------------------------------------------------------------------------
# 4. MAIN EXECUTION
# -------------------------------------------------------------------------

def main():
    """Main execution flow: Generate tree → Generate test cases → Write files."""
    
    print("="*70)
    print("MCP Safety Test Generator - FileSystem")
    print("="*70)
    
    # Configuration
    MCP_NAME = "FileSystem"
    MCP_TOOLS = [
        'read_file', 'read_text_file', 'read_media_file', 'read_multiple_files',
        'write_file', 'edit_file', 'create_directory', 'list_directory',
        'list_directory_with_sizes', 'directory_tree', 'move_file',
        'search_files', 'get_file_info', 'list_allowed_directories'
    ]
    
    # Phase 1: Generate safety analysis tree
    print(f"\n📊 Phase 1: Generating Safety Analysis Tree...")
    print(f"   Analyzing {len(MCP_TOOLS)} {MCP_NAME} functions")
    
    tree_data = generate_safety_tree(MCP_NAME, MCP_TOOLS)
    
    # Save tree for reference
    tree_file = BASE_OUTPUT_DIR / "safety_tree.json"
    BASE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(tree_file, 'w') as f:
        json.dump(tree_data, f, indent=2)
    print(f"✓ Tree generated and saved to: {tree_file}\n")
    
    # Phase 2: Generate test cases from tree
    print("📝 Phase 2: Generating Test Cases from Tree...")
    print(f"   Output directory: {BASE_OUTPUT_DIR}\n")
    
    task_counter = 1
    generated_tasks = []
    
    # Collect all scenarios (no filtering)
    scenarios_to_generate = []
    functions_with_harms = set()

    for child in tree_data.get('children', []):
        func_name = child['function']
        capability = child.get('capability', 'Unknown capability')
        
        # Collect harmful scenarios
        for scenario in child.get('harm_scenarios', []):
            harm = scenario['harm']
            test_desc = scenario['test_case_desc']
            
            scenarios_to_generate.append({
                "task_number": task_counter,
                "function": func_name,
                "capability": capability,
                "harm": harm,
                "test_case_desc": test_desc,
                "is_benign": False
            })
            task_counter += 1
            functions_with_harms.add(func_name)

    # Generate ONE benign case per function that has harms
    for child in tree_data.get('children', []):
        func_name = child['function']
        capability = child.get('capability', 'Unknown capability')
        
        if func_name in functions_with_harms:
            print(f"  Generating benign case for {func_name}...")
            benign_case = generate_benign_task(func_name, capability, MCP_NAME)
            
            scenarios_to_generate.append({
                "task_number": task_counter,
                "function": func_name,
                "capability": capability,
                "harm": None,
                "test_case_desc": benign_case['test_case_desc'],
                "is_benign": True,
                "benign_purpose": benign_case['purpose']
            })
            task_counter += 1

    print(f"   Total scenarios: {len(scenarios_to_generate)}")
    print(f"   Harmful: {len([s for s in scenarios_to_generate if not s['is_benign']])}")
    print(f"   Benign: {len([s for s in scenarios_to_generate if s['is_benign']])}\n")
    
    def process_scenario(scenario_info):
        """Process a single scenario (for multi-threading)"""
        task_num = scenario_info['task_number']
        func_name = scenario_info['function']
        harm = scenario_info.get('harm')  # Could be None for benign
        test_desc = scenario_info['test_case_desc']
        is_benign = scenario_info.get('is_benign', False)
        
        if is_benign:
            print(f"[Task {task_num}] {func_name} → BENIGN USE CASE")
        else:
            print(f"[Task {task_num}] {func_name} → {harm}")
        print(f"          {test_desc[:80]}...")
        
        node_info = {
            "function": func_name,
            "capability": scenario_info['capability'],
            "harm": harm if not is_benign else "benign_use_case",
            "test_case_desc": test_desc,
            "is_benign": is_benign,
            "benign_purpose": scenario_info.get('benign_purpose', '')
        }
        
        try:
            files_content = generate_task_files(node_info, MCP_NAME, is_benign=is_benign)
            task_dir = create_task_directory(task_num)
            
            # Extract setup files if present
            setup_files = files_content.get("setup_files", {})
            
            write_task_files(
                task_dir,
                files_content["task_md"],
                files_content["evaluator_py"],
                setup_files
            )
            
            if setup_files:
                print(f"          ✓ Created at: {task_dir} ({len(setup_files)} setup files)\n")
            else:
                print(f"          ✓ Created at: {task_dir}\n")
            
            return {
                "task_number": task_num,
                "function": func_name,
                "type": "benign" if is_benign else "harmful",
                "harm": harm,
                "path": str(task_dir)
            }
        except Exception as e:
            print(f"          ✗ Error: {e}\n")
            return None
    
    # Use ThreadPoolExecutor for parallel generation
    max_workers = min(5, len(scenarios_to_generate))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_scenario = {
            executor.submit(process_scenario, scenario): scenario
            for scenario in scenarios_to_generate
        }
        
        for future in as_completed(future_to_scenario):
            result = future.result()
            if result is not None:
                generated_tasks.append(result)
    
    # Summary
    print("="*70)
    print(f"✓ Generation Complete!")
    print(f"  Total tasks generated: {len(generated_tasks)}")
    print(f"  Output directory: {BASE_OUTPUT_DIR}")
    print("="*70)
    
    # Save summary
    summary_file = BASE_OUTPUT_DIR / "generation_summary.json"
    with open(summary_file, 'w') as f:
        json.dump({
            "mcp_name": MCP_NAME,
            "total_tasks": len(generated_tasks),
            "tasks": generated_tasks
        }, f, indent=2)
    print(f"\n📋 Summary saved to: {summary_file}")


if __name__ == "__main__":
    main()