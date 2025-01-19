from typing import Dict, List, Annotated, TypedDict, Optional
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor
import tiktoken
from dataclasses import dataclass
from collections import defaultdict
from app.core.config import settings

system_prompt = """
    You are PR-Reviewer, an advanced model designed to provide precise, constructive feedback and actionable code improvement suggestions for Git Pull Requests (PRs). 
    Your primary task is to analyze the PR diff (lines prefixed with `+`) and offer meaningful insights that improve code quality and address potential issues.

    ---

    ### Guidelines:
    1. Focus Areas:
    - Identify and address code problems, bugs, error handling or logical issues.
    - Suggest improvements for performance, modularity, and adherence to best practices.
    - Ensure your feedback is relevant and avoids duplicating changes already implemented in the PR.
    2. **Avoid suggesting**: 
    - Adding docstrings, type hints, or comments unless absolutely necessary.
    3. Ensure feedback is **concise** and actionable.

    ### Security Analysis:
    - **Check for vulnerabilities** such as sensitive information exposure, SQL injection, cross-site scripting (XSS), or other security risks.
    - If a vulnerability is detected, begin with a header (e.g., `Sensitive information exposure: ...`) and provide a clear explanation of the issue along with mitigation strategies.
    - If no vulnerabilities are found for a file, Do not mention in the `response

    ---

    ### Output Format:
    Respond in the json following structured format strictly:
    {
        "files": [
            {
                "name": "filename.py",
                "issues": [
                    {
                        "type": "issue_type",
                        "line": line_number,
                        "description": "Detailed description of the issue.",
                        "suggestion": "Actionable suggestion to resolve the issue."
                    }
                ],
                "code_suggestions": [
                    {
                        "line": line_number,
                        "suggestion": "Actionable suggestion to improve the code."
                    }
                ],
                "security_analysis": "No vulnerabilities detected or a detailed explanation of the vulnerabilities found."
            }
        ]
    }

    ---

    ### Example Scenarios for Feedback:
    1. **Bug Detection**: Identify logical errors or broken code paths.
    - Example: Detect and highlight unreachable code or incorrect logic.
    2. **Performance Improvements**: Suggest optimizations for slow or inefficient code.
    - Example: Recommend using a list comprehension instead of a for loop where appropriate.
    3. **Modularity and Best Practices**: Improve code organization, reuse, or adherence to coding standards.
    - Example: Recommend extracting repeated logic into helper functions.

    Deliver feedback that is concise, focused, and actionable, enabling developers to address issues efficiently while improving the overall code quality.
"""

language_map = {
            'py': 'python',
            'js': 'javascript',
            'jsx': 'javascript',
            'ts': 'typescript',
            'tsx': 'typescript',
            'md': 'markdown',
            'txt': 'text',
        }

# Data structures
@dataclass
class FilePatch:
    filename: str
    content: str
    language: str
    tokens: int = 0

class PRState(TypedDict):
    files: List[FilePatch]
    deleted_files: List[str]
    is_long_pr: bool
    organized_patches: Dict[str, List[FilePatch]]
    other_modified_files: List[FilePatch]
    current_batch: List[FilePatch]
    review_segments: List[str]
    other_files_summary: List[str]
    final_review: str

# Constants
TOKEN_LIMIT = 4000
LONG_PR_THRESHOLD = 3000
BATCH_SIZE = 2000
OTHER_FILES_CHUNK_SIZE = 1500  # Token limit for each chunk of other files

class PRProcessor:
    def __init__(self):
        self.tokenizer = tiktoken.encoding_for_model("gpt-4")
    
    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))
    
    def detect_language(self, filename: str) -> str:
        extension = filename.split('.')[-1].lower()
        return language_map.get(extension, 'unknown')
    
    def organize_patches(self, patches: List[FilePatch]) -> tuple[Dict[str, List[FilePatch]], List[FilePatch]]:
        """Organize patches and separate out overflow files."""
        language_patches = defaultdict(list)
        total_tokens = 0
        main_patches = []
        other_modified = []

        # First pass: count tokens and sort by size
        for patch in patches:
            patch.tokens = self.count_tokens(patch.content)
        sorted_patches = sorted(patches, key=lambda x: x.tokens, reverse=True)

        # Second pass: distribute patches
        for patch in sorted_patches:
            if total_tokens + patch.tokens <= TOKEN_LIMIT:
                language_patches[patch.language].append(patch)
                total_tokens += patch.tokens
                main_patches.append(patch)
            else:
                other_modified.append(patch)

        return language_patches, other_modified

    def chunk_other_files(self, files: List[FilePatch]) -> List[List[FilePatch]]:
        """Split other modified files into manageable chunks."""
        chunks = []
        current_chunk = []
        current_tokens = 0

        for file in files:
            if current_tokens + file.tokens > OTHER_FILES_CHUNK_SIZE and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0
            
            current_chunk.append(file)
            current_tokens += file.tokens

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

# LangGraph nodes
class PRReviewNodes:
    def __init__(self):
        self.llm = ChatOpenAI(openai_api_key = settings.OPENAI_API_KEY ,model_name="gpt-4", temperature=0)
        self.processor = PRProcessor()
    
    def analyze_pr_size(self, state: PRState) -> PRState:
        """Analyze PR size and organize patches if needed."""
        total_tokens = sum(self.processor.count_tokens(patch.content) for patch in state["files"])
        state["is_long_pr"] = total_tokens > LONG_PR_THRESHOLD
        
        if state["is_long_pr"]:
            organized, other_modified = self.processor.organize_patches(state["files"])
            state["organized_patches"] = organized
            state["other_modified_files"] = other_modified
            state["current_batch"] = []
        
        return state
    
    def review_short_pr(self, state: PRState) -> PRState:
        """Review a short PR in one go."""

        # Define the human prompt with placeholders
        human_prompt = """
        Review the following PR changes:

        {files_content}

        Deleted files:
        {deleted_files}

        Please provide:
        1. A summary of the changes
        2. Potential issues or concerns
        3. Suggestions for improvement
        4. Overall assessment
        """

        # Prepare content for placeholders
        files_content = "\n\n".join([
            f"File: {patch.filename} ({patch.language})\n```{patch.language}\n{patch.content}\n```"
            for patch in state.get("files", [])
        ])
        deleted_files_content = "\n".join(f"- {f}" for f in state.get("deleted_files", []))

        # Create the list of messages
        messages = [
            {"role": "system", "content": system_prompt.strip()},
            {
                "role": "human",
                "content": human_prompt.format(
                    files_content=files_content,
                    deleted_files=deleted_files_content,
                ).strip(),
            },
        ]

        # Send the messages to the LLM
        response = self.llm.invoke(messages)

        # Store the final review in the state
        state["final_review"] = response.content
        return state

    def summarize_other_files(self, state: PRState) -> PRState:
        """Summarize other modified files in chunks."""
        if not state["other_modified_files"]:
            return state

        chunks = self.processor.chunk_other_files(state["other_modified_files"])
        summaries = []

        prompt = ChatPromptTemplate.from_messages([
            ("human", """Provide a brief summary of these additional modified files:
            
            {files_content}
            
            Focus on:
            1. Key changes (2-3 sentences per file)
            2. Any potential risks or concerns""")
        ])

        for chunk in chunks:
            files_content = "\n\n".join([
                f"File: {patch.filename} ({patch.language})\n```{patch.language}\n{patch.content}\n```"
                for patch in chunk
            ])

            response = self.llm.invoke(prompt.format(files_content=files_content))
            summaries.append(response.content)

        state["other_files_summary"] = summaries
        return state
    
    def prepare_next_batch(self, state: PRState) -> PRState:
        """Prepare the next batch of files for review in a long PR."""
        current_tokens = 0
        current_batch = []
        
        for language, patches in state["organized_patches"].items():
            if not patches:
                continue
                
            while patches and current_tokens < BATCH_SIZE:
                patch = patches[0]
                if current_tokens + patch.tokens <= BATCH_SIZE:
                    current_batch.append(patches.pop(0))
                    current_tokens += patch.tokens
                else:
                    break
                    
        state["current_batch"] = current_batch
        return state
    
    def review_batch(self, state: PRState) -> PRState:
        """Review a batch of files from a long PR."""
        if not state["current_batch"]:
            return state
            
        prompt = ChatPromptTemplate.from_messages([
            
            ("human", """Review this batch of files from a larger PR:
            
            {files_content}
            
            Focus on:
            1. Key changes and their impact
            2. Potential issues
            3. Specific suggestions for this batch""")
        ])
       
        files_content = "\n\n".join([
            f"File: {patch.filename} ({patch.language})\n```{patch.language}\n{patch.content}\n```"
            for patch in state["current_batch"]
        ])
        print(files_content)
        
        response = self.llm.invoke(prompt.format(files_content=files_content))
        state["review_segments"].append(response.content)
        return state
    
    def create_final_review(self, state: PRState) -> PRState:
        """Synthesize all batch reviews into a final review."""
        
        # Define the human prompt with placeholders
        human_prompt = """
        Synthesize the PR review into a cohesive final review:

        Main Review Segments:
        {review_segments}

        Additional Modified Files Summary:
        {other_files_summary}

        Deleted Files:
        {deleted_files}

        Provide:
        1. Overall summary of changes
        2. Key concerns across all segments
        3. Major recommendations
        4. Final assessment
        """

        # Prepare content for placeholders
        deleted_files_content = "\n".join(f"- {f}" for f in state.get("deleted_files", []))
        review_segments_content = "\n\n---\n\n".join(state.get("review_segments", []))
        other_files_content = "\n\n".join(state.get("other_files_summary", [])) if state.get("other_files_summary") else "No additional files to summarize."

        # Combine messages
        messages = [
            {"role": "system", "content": system_prompt.strip()},
            {
                "role": "human",
                "content": human_prompt.format(
                    review_segments=review_segments_content,
                    other_files_summary=other_files_content,
                    deleted_files=deleted_files_content,
                ).strip(),
            },
        ]

        # Send the list of messages to the LLM
        response = self.llm.invoke(messages)

        # Store and return the final review
        # print("LLM Response:", response.content)
        state["final_review"] = response.content
        return state


def create_pr_review_graph() -> StateGraph:
    """Create the PR review workflow graph."""
    nodes = PRReviewNodes()
    
    # Create workflow graph
    workflow = StateGraph(PRState)
    
    # Add nodes
    workflow.add_node("analyze_pr_size", nodes.analyze_pr_size)
    workflow.add_node("review_short_pr", nodes.review_short_pr)
    workflow.add_node("prepare_next_batch", nodes.prepare_next_batch)
    workflow.add_node("review_batch", nodes.review_batch)
    workflow.add_node("summarize_other_files", nodes.summarize_other_files)
    workflow.add_node("create_final_review", nodes.create_final_review)
    
    # Define conditional edges using branches
    workflow.add_conditional_edges(
        "analyze_pr_size",
        lambda x: "review_short_pr" if not x["is_long_pr"] else "prepare_next_batch"
    )
    
    workflow.add_conditional_edges(
        "prepare_next_batch",
        lambda x: "review_batch" if bool(x["current_batch"]) else "summarize_other_files"
    )
    
    # Define regular edges
    workflow.add_edge("review_batch", "prepare_next_batch")
    workflow.add_edge("summarize_other_files", "create_final_review")
    
    # Set entry and exit points
    workflow.set_entry_point("analyze_pr_size")
    workflow.add_edge("review_short_pr", END)
    workflow.add_edge("create_final_review", END)
    
    return workflow

# Example usage
def review_pr(files: List[FilePatch], deleted_files: List[str]) -> str:
    """Review a PR using the LangGraph workflow."""
    workflow = create_pr_review_graph()
    
    # Initialize state
    state = PRState(
        files=files,
        deleted_files=deleted_files,
        is_long_pr=False,
        organized_patches={},
        other_modified_files=[],
        current_batch=[],
        review_segments=[],
        other_files_summary=[],
        final_review=""
    )
    
    # Run workflow
    app = workflow.compile()
    result = app.invoke(state)
    return result["final_review"]

def generate_pr_review(diff: List[dict]):
    def infer_language(filename: str) -> str:
        for extension, language in language_map.items():
            if filename.endswith(extension):
                return language
        return "unknown"
    
    # Sample PR data
    patches = []
    deleted_files = []
    for file in diff:
        filename = file["filename"]
        content = file.get("patch", "")
        language = infer_language(filename)
        status = file.get("status", "modified")
        if status == "deleted":
            deleted_files.append(filename)
        
        # Create a FilePatch instance
        file_patch = FilePatch(
            filename=filename,
            content=content,
            language=language,
        )
        patches.append(file_patch)

    
    # Run review
    review = review_pr(patches, deleted_files)
    print(review)
    return review


# # Example usage
# if __name__ == "__main__":
#     # Sample PR data
#     patches = [
#         FilePatch(
#             filename="main.py",
#             content="def hello():\n    printf('Hello, World!')",
#             language="python"
#         ),
#         FilePatch(
#             filename="utils.js",
#             content="const greet = () => console.log('Hi!');",
#             language="javascript"
#         )
#     ]
    
#     deleted_files = ["old_file.py", "deprecated.js"]
    
#     # Run review
#     review = review_pr(patches, deleted_files)
#     print(review)