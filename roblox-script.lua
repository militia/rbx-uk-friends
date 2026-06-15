-- Place this as a ServerScript in ServerScriptService
-- This game server is used by the Roblox Cloud API to execute friends lookups remotely.
-- No polling or HTTP requests are needed here — the server handles everything.
-- Just make sure the game has an active server session running.

local Players = game:GetService("Players")

local function getFriends(userId)
	local success, pages = pcall(function()
		return Players:GetFriendsAsync(userId)
	end)

	if not success then
		return nil, "GetFriendsAsync failed: " .. tostring(pages)
	end

	local friends = {}

	while true do
		local page = pages:GetCurrentPage()

		for _, f in ipairs(page) do
			table.insert(friends, {
				userId      = f.Id,
				username    = f.Username,
				displayName = f.DisplayName,
				isOnline    = f.IsOnline,
			})
		end

		if pages.IsFinished then
			break
		end

		local ok, err = pcall(function()
			pages:AdvanceToNextPageAsync()
		end)

		if not ok then
			warn("[FriendsAPI] Page advance failed: " .. tostring(err))
			break
		end
	end

	return friends
end

-- Expose via BindableFunction so other scripts can call getFriends locally
local bf = Instance.new("BindableFunction")
bf.Name = "GetFriends"
bf.Parent = script

bf.OnInvoke = function(userId)
	local friends, err = getFriends(userId)
	if err then
		return nil, err
	end
	return friends
end

print("[FriendsAPI] Ready — server is active for Cloud API execution")
