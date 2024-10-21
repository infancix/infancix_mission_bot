#!/bin/bash
input_image="input.jpg"  

# Get image dimensions
width=$(identify -format "%w" "$input_image")
height=$(identify -format "%h" "$input_image")

# Calculate new dimensions (50% of original size)
new_width=$((width / 2))
new_height=$((height / 2))

# Output image
output_image="output.jpg"

# Resize image to 50%
convert "$input_image" -resize "${new_width}x${new_height}" "$output_image"

