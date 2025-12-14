# Getting Started: The Complete Beginner's Guide
                           
Welcome! We're excited to have you. This guide is for anyone who is new to command-line tools or setting up development software. We'll walk you through every single step—no experience required.

Our goal is to get your computer ready so you can use the main **[5-Minute Quickstart](QUICKSTART.md)**. By the end of this guide, you will have:

1.  A command-line tool (the "terminal") ready to use.
2.  The Python programming language installed.
3.  The `scrappy` project code downloaded to your machine.

Let's begin!

---

## Step 1: Meet Your Command Line (The Terminal)

The command line—often called the **terminal**—is a text-based way to interact with your computer. Instead of clicking on icons, you type commands. It’s powerful, fast, and essential for many developer tools, including this one.

First, you need to open it.

**On Windows:**
1.  Click the Start button.
2.  Type `PowerShell`.
3.  Click on **"Windows PowerShell"** to open it. It will look like a blue or black window.

**On Mac:**
1.  Open Finder.
2.  Go to the "Applications" folder, then the "Utilities" folder.
3.  Double-click on **"Terminal"**.

**On Linux (Ubuntu/Debian):**
1.  Press `Ctrl+Alt+T` on your keyboard.
2.  Alternatively, find an application named **"Terminal"** in your app menu.

Great! You should now have a window with a blinking cursor. This is your terminal.

---

## Step 2: Install Python

`scrappy` is a Python application, so you need to have Python installed on your computer. Let's check if you already have it and install it if you don't.

### For Windows Users:

1.  Go to the official Python website: [https://www.python.org/downloads/](https://www.python.org/downloads/)
2.  Click the big yellow button that says "Download Python [version number]".
3.  Run the installer you just downloaded.
4.  **This is the most important step:** On the first screen of the installer, check the box at the bottom that says **"Add python.exe to PATH"**. This will save you a lot of trouble later!
5.  Click "Install Now" and follow the on-screen prompts.

### For Mac Users:

Newer versions of macOS come with Python pre-installed. Let's check.
1.  In your Terminal, type `python3 --version` and press Enter.
2.  If you see a version number (e.g., `Python 3.9.6`), you're all set!
3.  If you get an error, install it from the official website: [https://www.python.org/downloads/](https://www.python.org/downloads/)

### How to Verify Your Installation (All Users)

Once the installation is complete, close your terminal and open a **new one**. This is important for it to recognize the new software. Now, type the following two commands, pressing Enter after each one:

```bash
python --version
pip --version
```
*(Note: Mac and Linux users might need to use `python3` and `pip3`)*

If you see version numbers for both, you have successfully installed Python. Congratulations!

---

## Step 3: Get the Project Code

Now, you need to download the `scrappy` code to your computer.

1.  Go to the [project's repository page on GitHub](https://github.com/HakAl/scrappy).
2.  Look for a green "<> Code" button. Click it.
3.  In the dropdown menu, click **"Download ZIP"**.
4.  Save the file to a memorable location, like your **Desktop**.
5.  Find the downloaded ZIP file (e.g., `scrappy-main.zip`) and **unzip it**. You can usually do this by right-clicking and selecting "Extract All..." or "Unzip".
6.  You will now have a folder. Rename it to something simple: `scrappy`.

---

## Step 4: Run Your First Commands

You're almost there! Now we'll use the terminal to navigate into the project folder and install the application.

1.  **Navigate to the Folder:** In your terminal, you'll use the `cd` (Change Directory) command.
    *   If you saved the `scrappy` folder on your Desktop, you would type:
        ```bash
        cd Desktop/scrappy
        ```
    *   *Pro Tip: On Mac or Linux, you can type `cd ` (with a space) and then drag the folder from Finder directly into the terminal window. It will paste the correct path for you!*

2.  **Install the App:** Now that you are "inside" the project folder in your terminal, run the installation command. This command tells `pip` (Python's package installer) to set up the application and download anything it needs to run.
    ```bash
    pip install -e .
    ```
    *(Again, Mac/Linux users might need `pip3 install -e .`)*

    You will see text scroll by as it downloads and installs the necessary files. If it finishes without any big red "ERROR" messages, it worked!

---

## You're All Set!

Fantastic work! You have successfully set up your development environment. You've opened a terminal, installed Python, downloaded the code, and run your first installation command.

You are now fully prepared to continue with the main guide.

### **Next Step: [Return to the 5-Minute Quickstart](QUICKSTART.md)**

You can now follow that guide from the beginning. You've already done most of the work for the "Install" step, but it's good to start from the top to make sure everything is in order.