HUMAN_AGENTIC_PROMPT = """
You have access to math tools.
Call only the appropriate tools needed as much it is needed, don't unwantedly call unwanted tools
just let the tools do the work, your job is just to select the tools and not to answer on your own, If no tools are needed, dont use any and also dont answer on your own for the prompt

Task:
1. Multiply the output of sum of {0} and {1} with the greatest number among inputs of {0} and {1}

Use tools when needed.
Return only the final number.
"""
