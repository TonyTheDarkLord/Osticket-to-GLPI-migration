# Osticket-to-GLPI-migration

# # Intro

We used OSticket for about 7 years with about 45.000 tickets in the system but as the time of writing this(october 2024) It seems that no one cares and there is not support for the project at the time. No responsive or 2.0 version noticies with promises for the next year a RC(https://forum.osticket.com/d/105740-ost-20) that also was promised for this 2024(https://forum.osticket.com/d/102893-responsive-new-osticket-20-any-news), the lack of a good search, the windows 98 like interface, the strange mangement of permisions of tickets if a ticket came to two departments, the bugs in email fetching and some other things that my company wants. I understand that is not on purpose the delay and of course **I must thank all the team behind osticket for all this time and the support this years**. But I need more functionality and it seems that GLPI(that I already use it in other companies) is the best option out there.
To make this a dream come thru I first installed GLPI and then I configured the basics Entities, notifications, recievers, users, categories, groups and profiles.

# # The solution

> I must say that is not a perfect solution. In the transition more than 200 attachments and about 236 tickets didn't migrate at all, I assume the cost as I got 45.000 but I commend creating a copy before start and doing in batches to check for errors.

As 2024 I started with some help of claude.ai to make me the firsts functions. I lost 2 weeks tuning and fixing querys and also trying to do the migration as best as I can to make the transition the smoothest I could.
As I ship this script must be executed in osticket server, connects to database, and adds the tickets to glpi using the API. Creates User if not exists, also, adds follow ups with attachments ( this can be better but it's sufficient for me, now it adds to documents and then links it, but I know it can be added directly to follow up ), it permits to map agents from Osticket to GLPI technicians, also entities and statuses.

> After running it add user , password , database , glpi_url , glpi_app_token , glpi_user_token and corresponding maps in the functions \_map

I commented lots of print statements to prevent successful messages and left only errors for debugging.

Of course you can tweak as you want to make it work with more or less information, I made what work for me but the structure should work for any osticket running v1.18
