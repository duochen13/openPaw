/**
 * Nutrition API Integration
 *
 * Integrates with Nutritionix API to fetch nutrition data for menu items
 * Falls back to USDA FoodData Central (free) if Nutritionix is unavailable
 */

const https = require('https');
const { logger } = require('../utils/logger');
const { getSecret } = require('../utils/secrets');

/**
 * Make HTTPS request (Promise wrapper)
 */
function makeRequest(options, postData = null) {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            resolve(data);
          }
        } else {
          reject(new Error(`HTTP ${res.statusCode}: ${data}`));
        }
      });
    });

    req.on('error', reject);
    if (postData) {
      req.write(postData);
    }
    req.end();
  });
}

/**
 * Search Nutritionix for a food item
 * @param {string} query - Food item name (e.g., "Chipotle Burrito Bowl Chicken")
 * @param {Object} credentials - { appId, apiKey }
 * @returns {Object|null} Nutrition data or null
 */
async function searchNutritionix(query, credentials) {
  try {
    const { appId, apiKey } = credentials;

    const postData = JSON.stringify({ query });

    const options = {
      hostname: 'trackapi.nutritionix.com',
      port: 443,
      path: '/v2/natural/nutrients',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
        'x-app-id': appId,
        'x-app-key': apiKey
      }
    };

    const result = await makeRequest(options, postData);

    if (result.foods && result.foods.length > 0) {
      const food = result.foods[0];
      return {
        name: food.food_name,
        brand: food.brand_name || null,
        calories: Math.round(food.nf_calories || 0),
        protein: Math.round(food.nf_protein || 0),
        carbs: Math.round(food.nf_total_carbohydrate || 0),
        fat: Math.round(food.nf_total_fat || 0),
        servingSize: food.serving_qty || 1,
        servingUnit: food.serving_unit || 'serving',
        source: 'nutritionix'
      };
    }

    return null;
  } catch (error) {
    logger.warn('Nutritionix search failed', { query, error: error.message });
    return null;
  }
}

/**
 * Fallback: Search USDA FoodData Central (free)
 * @param {string} query - Food item name
 * @returns {Object|null} Nutrition data or null
 */
async function searchUSDA(query) {
  try {
    // USDA FoodData Central API (no key required for basic search)
    const searchUrl = `https://api.nal.usda.gov/fdc/v1/foods/search?query=${encodeURIComponent(query)}&pageSize=1&api_key=DEMO_KEY`;

    const options = {
      hostname: 'api.nal.usda.gov',
      port: 443,
      path: `/fdc/v1/foods/search?query=${encodeURIComponent(query)}&pageSize=1&api_key=DEMO_KEY`,
      method: 'GET',
      headers: {
        'Accept': 'application/json'
      }
    };

    const result = await makeRequest(options);

    if (result.foods && result.foods.length > 0) {
      const food = result.foods[0];
      const nutrients = food.foodNutrients || [];

      const getNutrient = (name) => {
        const nutrient = nutrients.find(n =>
          n.nutrientName && n.nutrientName.toLowerCase().includes(name.toLowerCase())
        );
        return nutrient ? Math.round(nutrient.value || 0) : 0;
      };

      return {
        name: food.description,
        brand: food.brandOwner || null,
        calories: getNutrient('Energy'),
        protein: getNutrient('Protein'),
        carbs: getNutrient('Carbohydrate'),
        fat: getNutrient('Total lipid'),
        servingSize: 100,
        servingUnit: 'g',
        source: 'usda'
      };
    }

    return null;
  } catch (error) {
    logger.warn('USDA search failed', { query, error: error.message });
    return null;
  }
}

/**
 * Get default nutrition estimate for unknown items
 * Uses average values for a typical meal
 */
function getDefaultEstimate(itemName) {
  logger.info('Using default nutrition estimate', { item: itemName });

  return {
    name: itemName,
    brand: null,
    calories: 500, // Average meal
    protein: 20,
    carbs: 60,
    fat: 15,
    servingSize: 1,
    servingUnit: 'serving',
    source: 'estimate',
    isEstimate: true
  };
}

/**
 * Match parsed receipt items to nutrition data
 * @param {Array} items - Array of { name, quantity, price }
 * @param {string} restaurant - Restaurant name (helps with matching)
 * @returns {Array} Items with nutrition data added
 */
async function matchNutrition(items, restaurant = '') {
  try {
    // Try to get Nutritionix credentials (optional)
    let nutritionixAppId, nutritionixApiKey;
    try {
      if (process.env.NUTRITIONIX_APP_ID_ARN && process.env.NUTRITIONIX_API_KEY_ARN) {
        [nutritionixAppId, nutritionixApiKey] = await Promise.all([
          getSecret(process.env.NUTRITIONIX_APP_ID_ARN),
          getSecret(process.env.NUTRITIONIX_API_KEY_ARN)
        ]);
      }
    } catch (err) {
      logger.info('Nutritionix credentials not available, will use USDA fallback');
    }

    const enrichedItems = [];

    for (const item of items) {
      // Build search query: "Restaurant Item Name"
      const searchQuery = restaurant
        ? `${restaurant} ${item.name}`
        : item.name;

      let nutritionData = null;

      // Try Nutritionix first (if available)
      if (nutritionixAppId && nutritionixApiKey) {
        nutritionData = await searchNutritionix(searchQuery, {
          appId: nutritionixAppId,
          apiKey: nutritionixApiKey
        });
      }

      // Fallback to USDA
      if (!nutritionData) {
        nutritionData = await searchUSDA(searchQuery);
      }

      // Last resort: use default estimate
      if (!nutritionData) {
        nutritionData = getDefaultEstimate(item.name);
      }

      // Multiply nutrition by quantity
      enrichedItems.push({
        ...item,
        nutrition: {
          ...nutritionData,
          // Total nutrition for quantity
          totalCalories: nutritionData.calories * item.quantity,
          totalProtein: nutritionData.protein * item.quantity,
          totalCarbs: nutritionData.carbs * item.quantity,
          totalFat: nutritionData.fat * item.quantity
        }
      });

      // Rate limiting: wait 100ms between requests
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    return enrichedItems;
  } catch (error) {
    logger.error('Nutrition matching failed', { error: error.message, stack: error.stack });
    // Return items with default estimates
    return items.map(item => ({
      ...item,
      nutrition: {
        ...getDefaultEstimate(item.name),
        totalCalories: 500 * item.quantity,
        totalProtein: 20 * item.quantity,
        totalCarbs: 60 * item.quantity,
        totalFat: 15 * item.quantity
      }
    }));
  }
}

/**
 * Calculate daily nutrition summary from multiple orders
 * @param {Array} orders - Array of parsed orders with nutrition data
 * @returns {Object} Daily summary
 */
function calculateDailySummary(orders) {
  const summary = {
    totalOrders: orders.length,
    totalSpent: 0,
    totalCalories: 0,
    totalProtein: 0,
    totalCarbs: 0,
    totalFat: 0,
    ordersByPlatform: {},
    estimatedItems: 0
  };

  for (const order of orders) {
    summary.totalSpent += order.total || 0;

    if (!summary.ordersByPlatform[order.platform]) {
      summary.ordersByPlatform[order.platform] = 0;
    }
    summary.ordersByPlatform[order.platform]++;

    for (const item of order.items) {
      if (item.nutrition) {
        summary.totalCalories += item.nutrition.totalCalories || 0;
        summary.totalProtein += item.nutrition.totalProtein || 0;
        summary.totalCarbs += item.nutrition.totalCarbs || 0;
        summary.totalFat += item.nutrition.totalFat || 0;

        if (item.nutrition.isEstimate) {
          summary.estimatedItems++;
        }
      }
    }
  }

  return summary;
}

module.exports = {
  matchNutrition,
  calculateDailySummary,
  searchNutritionix,
  searchUSDA
};
