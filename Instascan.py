"""
InstaScan - Advanced Instagram OSINT Tool
-----------------------------------------
A tool for ethical collection and analysis of publicly available Instagram profile information.
"""

import os
import sys
import json
import time
import argparse
import csv
import re
import datetime
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import instaloader

class InstaScan:
    def __init__(self, args):
        self.args = args
        self.results_dir = "results"
        self.target = args.username
        self.verbose = args.verbose
        self.output_format = args.output
        self.max_posts = args.max_posts
        self.timeout = args.timeout
        self.proxy = args.proxy
        self.session_file = args.session_file
        
        # Create results directory
        if not os.path.exists(self.results_dir):
            os.makedirs(self.results_dir)
            
        # Initialize instaloader
        self.L = instaloader.Instaloader(
            download_pictures=args.download_photos,
            download_videos=args.download_videos,
            download_video_thumbnails=False,
            download_geotags=True,
            download_comments=args.download_comments,
            save_metadata=True,
            compress_json=False
        )
        
        # Load session if provided
        if self.session_file:
            try:
                self.L.load_session_from_file(self.target, self.session_file)
                print(f"[+] Session loaded from {self.session_file}")
            except Exception as e:
                print(f"[!] Error loading session: {e}")
                print("[*] Continuing without authentication")
                
        # Use proxy if provided
        if self.proxy:
            os.environ['http_proxy'] = self.proxy
            os.environ['https_proxy'] = self.proxy

    def login(self, username, password):
        """Login to Instagram"""
        try:
            self.L.login(username, password)
            print(f"[+] Logged in as {username}")
            self.L.save_session_to_file()
            return True
        except Exception as e:
            print(f"[!] Login failed: {e}")
            return False

    def get_profile_data(self):
        """Get basic profile information"""
        try:
            profile = instaloader.Profile.from_username(self.L.context, self.target)
            
            profile_data = {
                "username": profile.username,
                "user_id": profile.userid,
                "full_name": profile.full_name,
                "biography": profile.biography,
                "external_url": profile.external_url,
                "followers_count": profile.followers,
                "following_count": profile.followees,
                "is_private": profile.is_private,
                "is_verified": profile.is_verified,
                "posts_count": profile.mediacount,
                "igtv_count": profile.igtvcount,
                "profile_pic_url": profile.profile_pic_url,
                "scrape_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            if self.verbose:
                print("\n[+] Profile Information:")
                for key, value in profile_data.items():
                    print(f"  - {key}: {value}")
            
            return profile, profile_data
            
        except instaloader.exceptions.ProfileNotExistsException:
            print(f"[!] Profile '{self.target}' does not exist")
            sys.exit(1)
        except Exception as e:
            print(f"[!] Error retrieving profile data: {e}")
            sys.exit(1)

    def analyze_posts(self, profile):
        """Analyze user posts for patterns and metadata"""
        if self.verbose:
            print("\n[+] Analyzing posts...")
        
        posts_data = []
        locations = []
        hashtags = {}
        mentions = {}
        post_times = []
        
        try:
            posts = profile.get_posts()
            
            for i, post in enumerate(posts):
                if i >= self.max_posts:
                    break
                    
                post_data = {
                    "shortcode": post.shortcode,
                    "url": f"https://www.instagram.com/p/{post.shortcode}/",
                    "timestamp": post.date_utc.strftime("%Y-%m-%d %H:%M:%S"),
                    "likes": post.likes,
                    "comments": post.comments,
                    "caption": post.caption if post.caption else "",
                    "location": post.location.name if post.location else None,
                    "hashtags": list(post.caption_hashtags),
                    "mentioned_users": list(post.caption_mentions),
                    "is_video": post.is_video
                }
                
                # Add to posts data
                posts_data.append(post_data)
                
                # Track post times for activity analysis
                post_times.append(post.date_utc)
                
                # Track locations
                if post.location:
                    locations.append({
                        "name": post.location.name,
                        "id": post.location.id,
                        "lat": post.location.lat,
                        "lng": post.location.lng,
                        "post_url": f"https://www.instagram.com/p/{post.shortcode}/"
                    })
                
                # Track hashtags
                for tag in post.caption_hashtags:
                    hashtags[tag] = hashtags.get(tag, 0) + 1
                
                # Track mentions
                for mention in post.caption_mentions:
                    mentions[mention] = mentions.get(mention, 0) + 1
                
                # Progress indicator
                if self.verbose:
                    sys.stdout.write(f"\r  - Processing post {i+1}/{self.max_posts}")
                    sys.stdout.flush()
            
            if self.verbose:
                print("\n  - Posts analyzed:", len(posts_data))
            
            # Sort hashtags and mentions by frequency
            top_hashtags = sorted(hashtags.items(), key=lambda x: x[1], reverse=True)
            top_mentions = sorted(mentions.items(), key=lambda x: x[1], reverse=True)
            
            # Analyze posting patterns
            time_patterns = self.analyze_posting_patterns(post_times)
            
            analysis_results = {
                "posts_analyzed": len(posts_data),
                "posts_data": posts_data,
                "locations": locations,
                "top_hashtags": top_hashtags[:20],
                "top_mentions": top_mentions[:20],
                "time_patterns": time_patterns
            }
            
            return analysis_results
            
        except Exception as e:
            print(f"\n[!] Error analyzing posts: {e}")
            return {
                "posts_analyzed": 0,
                "posts_data": [],
                "locations": [],
                "top_hashtags": [],
                "top_mentions": [],
                "time_patterns": {}
            }

    def analyze_posting_patterns(self, post_times):
        """Analyze posting patterns by time"""
        if not post_times:
            return {}
            
        days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_counts = {day: 0 for day in days_of_week}
        hour_counts = {hour: 0 for hour in range(24)}
        
        for post_time in post_times:
            day_counts[days_of_week[post_time.weekday()]] += 1
            hour_counts[post_time.hour] += 1
        
        most_active_day = max(day_counts.items(), key=lambda x: x[1])[0]
        most_active_hour = max(hour_counts.items(), key=lambda x: x[1])[0]
        
        return {
            "most_active_day": most_active_day,
            "day_activity": day_counts,
            "most_active_hour": most_active_hour,
            "hour_activity": hour_counts,
            "post_frequency_days": len(post_times) / (max((post_times[0] - post_times[-1]).days, 1)) if len(post_times) > 1 else 0
        }

    def analyze_connections(self, profile):
        """Analyze connections (followers/following)"""
        if profile.is_private:
            print("\n[!] Profile is private, cannot analyze connections")
            return {"followers": [], "following": []}
            
        if not self.L.context.is_logged_in:
            print("\n[!] Login required to analyze connections")
            return {"followers": [], "following": []}
            
        print("\n[+] Analyzing connections (this may take a while)...")
        
        followers = []
        following = []
        
        try:
            # Get followers
            print("  - Retrieving followers...")
            for follower in profile.get_followers():
                followers.append({
                    "username": follower.username,
                    "full_name": follower.full_name,
                    "is_verified": follower.is_verified
                })
                
            # Get following
            print("  - Retrieving following...")
            for followee in profile.get_followees():
                following.append({
                    "username": followee.username,
                    "full_name": followee.full_name,
                    "is_verified": followee.is_verified
                })
                
            # Find users who don't follow back
            not_following_back = [user["username"] for user in following 
                                 if user["username"] not in [f["username"] for f in followers]]
                                 
            # Find followers who aren't followed back
            not_followed_back = [user["username"] for user in followers 
                                if user["username"] not in [f["username"] for f in following]]
            
            connections_data = {
                "followers_count": len(followers),
                "following_count": len(following),
                "not_following_back": not_following_back,
                "not_followed_back": not_followed_back,
                "followers": followers,
                "following": following
            }
            
            return connections_data
            
        except Exception as e:
            print(f"[!] Error analyzing connections: {e}")
            return {"followers": [], "following": []}

    def search_external_references(self):
        """Search for external references to the username"""
        print("\n[+] Searching for external references...")
        
        sites_to_check = [
            f"https://twitter.com/{self.target}",
            f"https://www.facebook.com/{self.target}",
            f"https://www.tiktok.com/@{self.target}",
            f"https://www.reddit.com/user/{self.target}",
            f"https://www.linkedin.com/in/{self.target}",
            f"https://github.com/{self.target}",
            f"https://www.youtube.com/user/{self.target}"
        ]
        
        results = []
        
        def check_url(url):
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                response = requests.get(url, headers=headers, timeout=self.timeout)
                domain = urlparse(url).netloc.replace("www.", "")
                
                if response.status_code == 200:
                    return {
                        "platform": domain.split(".")[0].capitalize(),
                        "url": url,
                        "status": "Found",
                        "response_code": response.status_code
                    }
                else:
                    return {
                        "platform": domain.split(".")[0].capitalize(),
                        "url": url,
                        "status": "Not found",
                        "response_code": response.status_code
                    }
            except Exception as e:
                domain = urlparse(url).netloc.replace("www.", "")
                return {
                    "platform": domain.split(".")[0].capitalize(),
                    "url": url,
                    "status": "Error",
                    "response_code": str(e)
                }
        
        # Use ThreadPoolExecutor for parallel requests
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(check_url, sites_to_check))
        
        if self.verbose:
            print("  - External references found:")
            for result in results:
                if result["status"] == "Found":
                    print(f"    * {result['platform']}: {result['url']}")
        
        return results

    def export_results(self, profile_data, posts_analysis, connections=None, external_refs=None):
        """Export results to specified format"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{self.results_dir}/{self.target}_{timestamp}"
        
        # Prepare full results
        results = {
            "profile_data": profile_data,
            "posts_analysis": posts_analysis,
            "connections": connections if connections else {},
            "external_references": external_refs if external_refs else [],
            "scan_metadata": {
                "timestamp": timestamp,
                "tool": "InstaScan",
                "target": self.target
            }
        }
        
        # Export based on format
        if self.output_format == "json":
            with open(f"{output_file}.json", "w", encoding="utf-8") as f:
                json.dump(results, f, indent=4, ensure_ascii=False)
            print(f"\n[+] Results exported to {output_file}.json")
            
        elif self.output_format == "csv":
            # Export profile data
            with open(f"{output_file}_profile.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(profile_data.keys())
                writer.writerow(profile_data.values())
            
            # Export posts data
            if posts_analysis["posts_data"]:
                with open(f"{output_file}_posts.csv", "w", newline="", encoding="utf-8") as f:
                    keys = posts_analysis["posts_data"][0].keys()
                    writer = csv.DictWriter(f, fieldnames=keys)
                    writer.writeheader()
                    writer.writerows(posts_analysis["posts_data"])
            
            # Export locations
            if posts_analysis["locations"]:
                with open(f"{output_file}_locations.csv", "w", newline="", encoding="utf-8") as f:
                    keys = posts_analysis["locations"][0].keys()
                    writer = csv.DictWriter(f, fieldnames=keys)
                    writer.writeheader()
                    writer.writerows(posts_analysis["locations"])
                    
            print(f"\n[+] Results exported to {output_file}_*.csv files")
            
        else:  # text/stdout
            print("\n" + "="*50)
            print(f"RESULTS FOR @{self.target}")
            print("="*50)
            
            print("\nPROFILE INFORMATION:")
            for key, value in profile_data.items():
                print(f"  {key}: {value}")
                
            print("\nPOST ANALYSIS:")
            print(f"  Posts analyzed: {posts_analysis['posts_analyzed']}")
            print(f"  Locations found: {len(posts_analysis['locations'])}")
            
            if posts_analysis["time_patterns"]:
                patterns = posts_analysis["time_patterns"]
                print("\nPOSTING PATTERNS:")
                print(f"  Most active day: {patterns['most_active_day']}")
                print(f"  Most active hour: {patterns['most_active_hour']}:00")
                print(f"  Average post frequency: {patterns['post_frequency_days']:.2f} posts per day")
            
            if posts_analysis["top_hashtags"]:
                print("\nTOP HASHTAGS:")
                for tag, count in posts_analysis["top_hashtags"][:10]:
                    print(f"  #{tag}: {count}")
                    
            if posts_analysis["top_mentions"]:
                print("\nTOP MENTIONS:")
                for user, count in posts_analysis["top_mentions"][:10]:
                    print(f"  @{user}: {count}")
            
            if external_refs:
                print("\nEXTERNAL REFERENCES:")
                for ref in external_refs:
                    if ref["status"] == "Found":
                        print(f"  {ref['platform']}: {ref['url']}")

    def run(self):
        """Run the main scan process"""
        print(f"[+] Starting scan for Instagram user: @{self.target}")
        
        start_time = time.time()
        
        # Get profile data
        profile, profile_data = self.get_profile_data()
        
        # Check if profile is private
        if profile.is_private and not self.L.context.is_logged_in:
            print("[!] Profile is private. Login required to access content.")
            print("[*] Only basic profile information will be available.")
        
        # Analyze posts
        posts_analysis = self.analyze_posts(profile)
        
        # Analyze connections (only if logged in)
        connections = None
        if self.L.context.is_logged_in and not profile.is_private:
            connections = self.analyze_connections(profile)
        
        # Search for external references
        external_refs = self.search_external_references() if self.args.external_search else None
        
        # Export results
        self.export_results(profile_data, posts_analysis, connections, external_refs)
        
        elapsed_time = time.time() - start_time
        print(f"\n[+] Scan completed in {elapsed_time:.2f} seconds")


def main():
    """Main function to parse args and run the tool"""
    parser = argparse.ArgumentParser(description="InstaScan - Advanced Instagram OSINT Tool")
    
    parser.add_argument("username", help="Instagram username to scan")
    parser.add_argument("-o", "--output", choices=["json", "csv", "text"], default="text",
                        help="Output format (default: text)")
    parser.add_argument("-m", "--max-posts", type=int, default=50,
                        help="Maximum number of posts to analyze (default: 50)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose output")
    parser.add_argument("-dl", "--download-photos", action="store_true",
                        help="Download profile and post photos")
    parser.add_argument("-dlv", "--download-videos", action="store_true",
                        help="Download videos")
    parser.add_argument("-dlc", "--download-comments", action="store_true",
                        help="Download post comments")
    parser.add_argument("-l", "--login", nargs=2, metavar=("USERNAME", "PASSWORD"),
                        help="Login credentials (required for private profiles)")
    parser.add_argument("-s", "--session-file", help="Load session from file")
    parser.add_argument("-p", "--proxy", help="Proxy URL (e.g., http://127.0.0.1:8080)")
    parser.add_argument("-t", "--timeout", type=int, default=10,
                        help="Request timeout in seconds (default: 10)")
    parser.add_argument("-e", "--external-search", action="store_true",
                        help="Search for the username on other platforms")
    
    args = parser.parse_args()
    
    try:
        scanner = InstaScan(args)
        
        # Login if credentials provided
        if args.login:
            username, password = args.login
            if not scanner.login(username, password):
                print("[*] Continuing without authentication")
        
        # Run the scan
        scanner.run()
        
    except KeyboardInterrupt:
        print("\n[!] Scan interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] An error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
