from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_cors import CORS
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import os
from flask_babel import Babel
from datetime import datetime
from flask import jsonify
from flask import Flask, jsonify, request, session, redirect, url_for, flash
from bson import ObjectId
app = Flask(__name__)
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
babel = Babel(app)
app.secret_key = os.urandom(24)  # For production, use a fixed secret key
CORS(app)  # Enable CORS for all routes


# MongoDB setup
client = MongoClient("mongodb://localhost:27017/")
db_user = client['moviereview']
users_collection = db_user['users']

db_movies = client['userdb']
movies_collection = db_movies['movie']
# Ensure the profile_pictures directory exists
os.makedirs('static/profile_pictures', exist_ok=True)

# Updated format_date filter to accept both arguments
@app.template_filter('date')
def format_date(value, format='%B %d, %Y'):  # Second argument is optional for flexibility
    if isinstance(value, datetime):
        return value.strftime(format)  # Format to "Month Day, Year"
    return value


# Home route - Redirect to dashboard if logged in, else to login
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('head'))
    return render_template('index.html')  # Display index.html as the first page

# Signup route (GET and POST)
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form['fullname']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        profile_picture = request.files.get('profile_picture')  # Get the uploaded file

        # Basic validation
        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return redirect(url_for('signup'))

        # Check if user already exists
        existing_user = users_collection.find_one({'email': email})
        if existing_user:
            flash("Email already registered. Please log in.", "warning")
            return redirect(url_for('login'))

        # Hash the password
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Create user data
        profile_picture_filename = None
        if profile_picture:
            profile_picture_filename = f"{email}.jpg"  # Use email as filename (or any unique identifier)
            profile_picture.save(os.path.join('static/profile_pictures', profile_picture_filename))

        user_data = {
            'fullname': fullname,
            'email': email,
            'password': hashed_password,
            'profile_picture': profile_picture_filename  # Store the filename in the database
        }

        # Insert into MongoDB
        users_collection.insert_one(user_data)
        flash("Signup successful! Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')
# Login route (GET and POST)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Find user by email
        user = users_collection.find_one({'email': email})
        if user and check_password_hash(user['password'], password):
            # Set session
            session['user_id'] = str(user['_id'])
            session['fullname'] = user['fullname']
            flash("Logged in successfully!", "success")
            return redirect(url_for('head'))  # Redirect to the head page
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for('login'))

    return render_template('login.html')

# Head page route with navigation buttons
@app.route('/head')
def head():
    if 'user_id' not in session:
        flash("Please log in to access this page.", "warning")
        return redirect(url_for('login'))
    return render_template('head_page.html')  # Updated to head_page.html

# Profile route - Updated to handle picture upload
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash("Please log in to access the profile.", "warning")
        return redirect(url_for('login'))

    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})

    if request.method == 'POST':
        # Handle profile picture update
        profile_picture = request.files.get('profile_picture')
        if profile_picture:
            profile_picture_filename = f"{user['email']}.jpg"  # Use email for filename
            profile_picture.save(os.path.join('static/profile_pictures', profile_picture_filename))

            # Update user document with new profile picture
            users_collection.update_one(
                {"_id": ObjectId(session['user_id'])},
                {"$set": {"profile_picture": profile_picture_filename}}
            )
            flash("Profile picture updated successfully!", "success")
        else:
            flash("No picture uploaded.", "warning")

    user_profile = {
        'fullname': user['fullname'],
        'email': user['email'],
        'profile_picture': user.get('profile_picture', None),  # Fetch profile picture filename
        'watchlist': user.get('watchlist', []),
        'liked_movies': user.get('liked_movies', []),
        'disliked_movies': user.get('disliked_movies', [])
    }

    return render_template('profile.html', profile=user_profile)
# Dashboard route for movie search
@app.route('/dash', methods=['GET', 'POST'])
def dash():
    if 'user_id' not in session:
        flash("Please log in to access the dashboard.", "warning")
        return redirect(url_for('login'))

    movie = None
    movie_names = []

    if request.method == 'POST':
        selected_movie = request.form.get('movie_name')
        if selected_movie:
            return redirect(url_for('get_movie', movie_name=selected_movie))
        else:
            flash("Please select a movie to search.", "warning")
            return redirect(url_for('dash'))

    # Populate movie names for the dropdown
    try:
        movies_list = movies_collection.find().sort("Movie_Name", 1)
        movie_names = [movie['Movie_Name'] for movie in movies_list]
    except Exception as e:
        print("Error fetching movies from MongoDB:", e)

    return render_template('dash.html', movie=movie, movie_names=movie_names)

# Route to display movie details and reviews
@app.route('/movie/<string:movie_name>', methods=['GET'])
def get_movie(movie_name):
    if 'user_id' not in session:
        flash("Please log in to access the dashboard.", "warning")
        return redirect(url_for('login'))

    movie = movies_collection.find_one({"Movie_Name": {"$regex": f"^{movie_name}$", "$options": "i"}})
    if movie:
        movie['_id'] = str(movie['_id'])
        movie_names = [m['Movie_Name'] for m in movies_collection.find().sort("Movie_Name", 1)]
        reviews = movie.get("Reviews", [])
        return render_template('dash.html', movie=movie, movie_names=movie_names, reviews=reviews)
    else:
        flash("Movie not found.", "danger")
        return redirect(url_for('dash'))

# Route to add a review
@app.route('/movie/<string:movie_name>/review', methods=['POST'])
def add_review(movie_name):
    if 'user_id' not in session:
        flash("Please log in to add a review.", "warning")
        return redirect(url_for('login'))

    # Use .get() to avoid KeyError if the form field is missing
    review_text = request.form.get('review_text')  # Match the field name with the template
    reviewer = session.get('fullname')  # Automatically get the logged-in user's name

    # Debugging: Check if the form data is being correctly retrieved
    print(f"Review Text: {review_text}")
    print(f"Reviewer: {reviewer}")

    # Check if the review text is provided
    if not review_text or not review_text.strip():
        flash("Review cannot be empty!", "danger")
        return redirect(url_for('get_movie', movie_name=movie_name))

    new_review = {
        "Reviewer": reviewer,
        "Review_text": review_text.strip(),
        "date": datetime.utcnow()
    }

    # Debugging: Print the new review object
    print(f"New Review Object: {new_review}")

    # Update the movie document by pushing the new review into the Reviews array
    result = movies_collection.update_one(
        {"Movie_Name": {"$regex": f"^{movie_name}$", "$options": "i"}},
        {"$push": {"Reviews": new_review}}
    )

    # Debugging: Check the result of the update operation
    print(f"Update Result: {result.matched_count} matched, {result.modified_count} modified")

    if result.matched_count:
        flash("Review added successfully!", "success")
    else:
        flash("Failed to add review. Movie not found.", "danger")

    return redirect(url_for('get_movie', movie_name=movie_name))

# Route to edit a review using the review index in the array
@app.route('/movie/<string:movie_name>/review/edit/<int:review_index>', methods=['GET', 'POST'])
def edit_review(movie_name, review_index):
    if 'user_id' not in session:
        flash("Please log in to edit a review.", "warning")
        return redirect(url_for('login'))

    movie = movies_collection.find_one({"Movie_Name": movie_name})
    
    # Fetch the review using the index
    if movie and 0 <= review_index < len(movie["Reviews"]):
        review = movie["Reviews"][review_index]
    else:
        flash("Review not found.", "danger")
        return redirect(url_for('get_movie', movie_name=movie_name))

    # Ensure the logged-in user is the one who posted the review
    if review['Reviewer'] != session['fullname']:
        flash("You can only edit your own reviews.", "danger")
        return redirect(url_for('get_movie', movie_name=movie_name))

    if request.method == 'POST':
        updated_review_text = request.form.get('Review_text')
        # Validate if the review text is empty
        if not updated_review_text or not updated_review_text.strip():
            flash("Review cannot be empty!", "danger")
            return redirect(url_for('edit_review', movie_name=movie_name, review_index=review_index))

        # Update the review at the specific index
        movies_collection.update_one(
            {"Movie_Name": movie_name},
            {"$set": {f"Reviews.{review_index}.Review_text": updated_review_text.strip()}}
        )
        flash("Review updated successfully!", "success")
        return redirect(url_for('get_movie', movie_name=movie_name))

    # Pass review_index to the template
    return render_template('edit_review.html', movie=movie, review=review, review_index=review_index)


# Route to delete a review using the review index in the array
@app.route('/movie/<string:movie_name>/review/delete/<int:review_index>', methods=['POST'])
def delete_review(movie_name, review_index):
    if 'user_id' not in session:
        flash("Please log in to delete a review.", "warning")
        return redirect(url_for('login'))

    movie = movies_collection.find_one({"Movie_Name": movie_name})

    # Validate the review index
    if movie and 0 <= review_index < len(movie["Reviews"]):
        review = movie["Reviews"][review_index]
        # Ensure the logged-in user is the one who posted the review
        if review['Reviewer'] != session['fullname']:
            flash("You can only delete your own reviews.", "danger")
            return redirect(url_for('get_movie', movie_name=movie_name))

        # Remove the review at the specified index
        movies_collection.update_one(
            {"Movie_Name": movie_name},
            {"$pull": {"Reviews": movie["Reviews"][review_index]}}
        )
        flash("Review deleted successfully!", "success")
    else:
        flash("Review not found.", "danger")

    return redirect(url_for('get_movie', movie_name=movie_name))

# Route to like a movie
@app.route('/movie/<string:movie_name>/like', methods=['POST'])
def like_movie(movie_name):
    if 'user_id' not in session:
        flash("Please log in to like a movie.", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    movie_name_normalized = movie_name.lower()  # Normalize movie name for consistency

    # Update the movie document to add the user's ID to the Likes array
    result = movies_collection.update_one(
        {"Movie_Name": {"$regex": f"^{movie_name}$", "$options": "i"}},
        {"$addToSet": {"Likes": user_id}}  # Use $addToSet to avoid duplicates
    )

    # Update user liked movies
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"liked_movies": movie_name_normalized}}  # Add movie name to the user's liked movies
    )

    if result.matched_count:
        flash("Movie liked successfully!", "success")
    else:
        flash("Failed to like movie. Movie not found.", "danger")

    return redirect(url_for('get_movie', movie_name=movie_name))


# Route to dislike a movie
@app.route('/movie/<string:movie_name>/dislike', methods=['POST'])
def dislike_movie(movie_name):
    if 'user_id' not in session:
        flash("Please log in to dislike a movie.", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    movie_name_normalized = movie_name.lower()  # Normalize movie name for consistency

    # Update the movie document to add the user's ID to the Dislikes array
    result = movies_collection.update_one(
        {"Movie_Name": {"$regex": f"^{movie_name}$", "$options": "i"}},
        {"$addToSet": {"Dislikes": user_id}}  # Use $addToSet to avoid duplicates
    )

    # Update user disliked movies
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"disliked_movies": movie_name_normalized}}  # Add movie name to the user's disliked movies
    )

    if result.matched_count:
        flash("Movie disliked successfully!", "success")
    else:
        flash("Failed to dislike movie. Movie not found.", "danger")

    return redirect(url_for('get_movie', movie_name=movie_name))
@app.route('/remove_from_watchlist/<string:movie_name>', methods=['POST'])
def remove_from_watchlist(movie_name):
    if 'user_id' not in session:
        flash("Please log in to remove a movie from your watchlist.", "warning")
        return redirect(url_for('login'))

    # Update the user's watchlist to remove the specified movie
    result = users_collection.update_one(
        {"_id": ObjectId(session['user_id'])},
        {"$pull": {"watchlist": movie_name}}
    )

    if result.modified_count > 0:
        flash(f"{movie_name} removed from your watchlist!", "success")
    else:
        flash(f"{movie_name} was not in your watchlist.", "warning")

    return redirect(url_for('profile'))  # Redirect back to the profile page


# Logout route
@app.route('/logout')
def logout():
    session.clear()  # Clear the session
    flash("Logged out successfully!", "success")
    return redirect(url_for('login'))  # Redirect to login page
@app.route('/recommend', methods=['GET', 'POST'])
def recommend_movies():
    if request.method == 'POST':
        # Get the user's selected genre and rating threshold from the form
        selected_genre = request.form.get('genre')
        min_rating = float(request.form.get('rating', 8))  # Default rating above 8 if not specified

        # Query to find top 5 movies that match the genre and have a rating above the threshold
        recommended_movies = movies_collection.find({
            "Genre": selected_genre,
            "Rating": {"$gte": min_rating}
        }).sort("Rating", -1).limit(5)  # Sort by rating in descending order and limit to top 5

        # Convert the cursor to a list of movie dictionaries
        recommended_movies_list = list(recommended_movies)

        return render_template(
            'recommendations.html',
            movies=recommended_movies_list,
            genre=selected_genre,
            rating=min_rating,
            no_results=(len(recommended_movies_list) == 0)
        )

    # For GET requests, render the genre selection and rating input form
    genres = movies_collection.distinct("Genre")  # Get unique genres from the collection
    return render_template('recommend_form.html', genres=genres)

# Route to add a movie to the watchlist
@app.route('/add_to_watchlist/<string:movie_name>', methods=['POST'])
def add_to_watchlist(movie_name):
    if 'user_id' not in session:
        flash("Please log in to add a movie to your watchlist.", "warning")
        return redirect(url_for('login'))

    # Add the movie to the user's watchlist, avoiding duplicates with $addToSet
    users_collection.update_one(
        {"_id": ObjectId(session['user_id'])},
        {"$addToSet": {"watchlist": movie_name}}
    )

    flash(f"{movie_name} added to your watchlist!", "success")
    return redirect(url_for('get_movie', movie_name=movie_name))
if __name__ == '__main__':

    app.run(debug=True)  # Enable debug mode for development