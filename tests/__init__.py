"""
This file is intentionally left blank.

In Python, the presence of an __init__.py file tells the interpreter to treat 
the directory as a module. While modern pytest can often run without it, 
including an empty __init__.py in your tests/ folder is an Enterprise best practice. 

It guarantees that pytest can accurately resolve absolute imports 
(like `from src.extract import...`) and prevents namespace collisions if you 
have multiple files with the same name across different directories.
"""