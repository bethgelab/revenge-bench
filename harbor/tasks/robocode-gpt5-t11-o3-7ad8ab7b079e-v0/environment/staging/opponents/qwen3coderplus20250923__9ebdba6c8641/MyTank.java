package custom;

import robocode.*;
import robocode.util.Utils;
import java.awt.*;

public class MyTank extends AdvancedRobot {
    String targetName = null; // Name of the robot we're currently tracking
    int targetUnseenCount = 0; // How long since we last saw our target
    
    // Variables for predictive targeting
    double targetVelocity;
    double targetHeading;
    double targetDistance;
    double targetBearing;
    double targetEnergy;
    
    public void run() {
        // Set colors
        setBodyColor(new Color(50, 100, 200));
        setGunColor(new Color(100, 150, 255));
        setRadarColor(new Color(200, 100, 50));
        setScanColor(Color.white);
        setBulletColor(Color.red);

        // Set adjustment behaviors
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForRobotTurn(true);
        
        // Initialize movement
        setTurnRadarRightRadians(Double.POSITIVE_INFINITY);
        
        // Loop forever
        while (true) {
            // Move in a more unpredictable pattern
            moveUnpredictably();
            
            execute();
        }
    }

    public void moveUnpredictably() {
        // Implement a more sophisticated movement pattern
        // If we're near a wall, move away from it
        if (getX() < 100 || getX() > getBattleFieldWidth() - 100 || 
            getY() < 100 || getY() > getBattleFieldHeight() - 100) {
            // Near a wall, move toward center
            double centerAngle = Utils.normalAbsoluteAngle(Math.atan2(
                getBattleFieldWidth()/2 - getX(), 
                getBattleFieldHeight()/2 - getY()));
            double turn = Utils.normalRelativeAngle(centerAngle - getHeadingRadians());
            setTurnRightRadians(turn);
            setAhead(100);
        } else {
            // Not near a wall, implement a more random movement
            setTurnRight(45 + (Math.random() * 90 - 45)); // Random turn between 0 and 90 degrees
            setAhead(50 + (Math.random() * 100 - 50)); // Random movement between 0 and 100
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // If we have a target and this isn't it, return
        if (targetName != null && !e.getName().equals(targetName)) {
            return;
        }
        
        // If this is the first time seeing this robot, track it
        if (targetName == null) {
            targetName = e.getName();
        }
        
        // Reset unseen count
        targetUnseenCount = 0;
        
        // Update target information for predictive targeting
        targetBearing = e.getBearingRadians();
        targetDistance = e.getDistance();
        targetHeading = e.getHeadingRadians();
        targetVelocity = e.getVelocity();
        targetEnergy = e.getEnergy();
        
        // Calculate enemy position
        double absoluteBearing = getHeadingRadians() + targetBearing;
        double enemyX = getX() + targetDistance * Math.sin(absoluteBearing);
        double enemyY = getY() + targetDistance * Math.cos(absoluteBearing);
        
        // Predict enemy position based on velocity and heading
        double bulletPower = Math.min(3.0, Math.max(0.1, 400.0 / targetDistance));
        double bulletSpeed = 20.0 - bulletPower * 3.0;
        double timeToHit = targetDistance / bulletSpeed;
        
        // Predict where the enemy will be when our bullet arrives
        double predictedX = enemyX + Math.sin(targetHeading) * targetVelocity * timeToHit;
        double predictedY = enemyY + Math.cos(targetHeading) * targetVelocity * timeToHit;
        
        // Calculate the angle to the predicted position
        double predictedBearing = Utils.normalAbsoluteAngle(Math.atan2(
            predictedX - getX(), 
            predictedY - getY()));
        
        // Aim and fire at the predicted position
        double gunTurn = Utils.normalRelativeAngle(predictedBearing - getGunHeadingRadians());
        setTurnGunRightRadians(gunTurn);
        
        // Adjust firepower based on distance and enemy energy change
        double firepower = Math.min(3.0, Math.max(0.1, 400.0 / targetDistance));
        
        // Fire with calculated power
        setFire(firepower);
        
        // If enemy is far away, move toward them
        if (targetDistance > 200) {
            double turn = Utils.normalRelativeAngle(absoluteBearing - getHeadingRadians());
            setTurnRightRadians(turn);
            setAhead(100);
        } 
        // If enemy is too close, move away
        else if (targetDistance < 100) {
            double turn = Utils.normalRelativeAngle(absoluteBearing - getHeadingRadians());
            setTurnRightRadians(turn + Math.PI); // Turn around
            setAhead(100);
        }
        
        // Move radar to keep tracking
        setTurnRadarRightRadians(Utils.normalRelativeAngle(absoluteBearing - getRadarHeadingRadians()));
    }

    public void onHitByBullet(HitByBulletEvent e) {
        // Change direction when hit
        setTurnRight(90 + (Math.random() * 60 - 30)); // Add some randomness
        setAhead(100);
    }

    public void onHitRobot(HitRobotEvent e) {
        // If we hit another robot, fire with max power
        double gunTurn = Utils.normalRelativeAngle((getHeadingRadians() + e.getBearingRadians()) - getGunHeadingRadians());
        setTurnGunRightRadians(gunTurn);
        setFire(3);
        
        // Move away from the robot we hit
        setTurnRight(e.getBearing() + 180);
        setAhead(100);
    }
    
    public void onRobotDeath(RobotDeathEvent e) {
        // If our target died, reset target
        if (e.getName().equals(targetName)) {
            targetName = null;
        }
    }
    
    public void onWin() {
        // Victory dance
        for (int i = 0; i < 5; i++) {
            setTurnRight(72);
            setAhead(50);
            execute();
        }
    }
}