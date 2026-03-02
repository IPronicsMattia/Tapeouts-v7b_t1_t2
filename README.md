# IPronics Layout library for Tower V7a
![logo](https://github.com/iPronics/IPRLAYOUT_Tower/blob/feature/clean_first_update/img/logo.png)

## Requirements
For using this module you need to have installed:
  1. Mambaforge or anaconda.
  2. Python >=3.10

You can download anaconda from https://www.anaconda.com/docs/getting-started/anaconda/install  
Or
You can download mambaforge from https://github.com/conda-forge/miniforge  

Choose wichever you prefer!

## Installation
Once you have mamba/conda installed, follow the next steps:

  1. Clone this repository.

  2. Activate conda/mamba by entering the following code (replace with your username and/or path of installation):  
     Conda:
     ```
       C:\Anaconda\Scripts\activate
     ```
     Mamba:
     ```
      C:\Users\UserName\mambaforge\Scripts\activate
      ```

     You can also type in the terminal the following commands if you have the environment variables set:  
     Conda:
     ```
       conda activate
     ```
     Mamba:
     ```
      mamba activate
      ```

  3. It is highly recommended to create a new environment:  
     Conda:
     ```
       conda create -n name_of_the_environment python=3.11
     ```
     Mamba:
     ```
      mamba create -n name_of_the_environment
     ```

  4. Activate the environment:  
     Conda:
     ```
       conda activate name_of_the_environment
     ```
     Mamba:
     ```
      mamba activate name_of_the_environment
      ```

  5. Install dependencies, you can install each dependency of the library (python, black...) or just install this module with all its dependencies:  
     You need to be in the directory where the pyproject.toml file is located for pip to work!  
     Conda & Mamba:
     ```
      pip install -e .
      ```
