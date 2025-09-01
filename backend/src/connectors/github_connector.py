
import requests
import os
from dotenv import load_dotenv

class GithubConnector:
    def __init__(self, github_token):
        self.github_token = github_token
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {self.github_token}"
        }

    def get_user_repos(self, username):
        """
        Fetches public repositories for a given GitHub user.
        :param username: The GitHub username.
        :return: A list of dictionaries containing repository details, or None if not found/error.
        """
        url = f"https://api.github.com/users/{username}/repos"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching repositories for {username}: {e}")
            return None

    def get_repo_details(self, owner, repo_name):
        """
        Fetches details for a specific repository.
        :param owner: The owner of the repository.
        :param repo_name: The name of the repository.
        :return: A dictionary containing repository details, or None if not found/error.
        """
        url = f"https://api.github.com/repos/{owner}/{repo_name}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching details for {owner}/{repo_name}: {e}")
            return None

    def get_repo_contents(self, owner, repo_name, path=""):
        """
        Fetches the contents (files and directories) of a specific path within a repository.
        :param owner: The owner of the repository.
        :param repo_name: The name of the repository.
        :param path: The path within the repository (e.g., "src/main"). Defaults to root.
        :return: A list of dictionaries containing content details, or None if not found/error.
        """
        url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{path}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching contents for {owner}/{repo_name}/{path}: {e}")
            return None

# Example Usage
if __name__ == "__main__":
    load_dotenv() # Load environment variables from .env file

    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    GITHUB_REPO = os.getenv("GITHUB_REPO") # Optional, for testing get_user_repos
    GITHUB_USERNAME = os.getenv("GITHUB_USERNAME") # Optional, for testing get_user_repos

    if not GITHUB_TOKEN:
        print("Error: Please set GITHUB_TOKEN in your .env file.")
    else:
        connector = GithubConnector(GITHUB_TOKEN)

        # Example: Get repositories for a user
        if GITHUB_USERNAME:
            print(f"\n--- Repositories for {GITHUB_USERNAME} ---")
            user_repos = connector.get_user_repos(GITHUB_USERNAME)
            if user_repos:
                for repo in user_repos:
                    print(f"Repo Name: {repo.get('name')}, Stars: {repo.get('stargazers_count')}")
            else:
                print("Failed to fetch user repositories.")

        
        repo_details = connector.get_repo_details("dhruva-nu", "ProjectMannagee_2")
        if repo_details:
            print(f"Repo Name: {repo_details.get('name')}")
            print(f"Description: {repo_details.get('description')}")
            print(f"Stars: {repo_details.get('stargazers_count')}")
        else:
            print("Failed to fetch repository details.")


